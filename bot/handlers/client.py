"""Сценарий клиента: услуга → дата → время → имя → телефон → подтверждение.

Параметры repo, config и bot aiogram подставляет в обработчики сам —
по имени, из того, что положено в Dispatcher в __main__.py.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot import keyboards as kb
from bot import texts
from bot.config import Config
from bot.db import TIME_FMT, BookingRepo, NewBooking
from bot.handlers.common import edit_message as _edit
from bot.notify import notify_admins
from bot.schedule import REMINDER_BEFORE_MIN, Service, candidate_dates, free_slots, get_service
from bot.validators import normalize_name, normalize_phone

router = Router(name="client")
MY_BOOKINGS_HORIZON = timedelta(days=60)


class BookingForm(StatesGroup):
    """Шаги, на которых бот ждёт от клиента текст, а не нажатие кнопки."""

    name = State()
    phone = State()
    confirm = State()


# ---- Вспомогательные функции ------------------------------------------------

async def _dates_with_slots(repo: BookingRepo, config: Config, service: Service) -> List[date]:
    now = config.now()
    result = []
    for day in candidate_dates(now.date()):
        busy = await repo.busy_intervals(day)
        if free_slots(day, service.duration_min, busy, now):
            result.append(day)
    return result


async def _slots_for(repo: BookingRepo, config: Config, service: Service, day: date) -> List[datetime]:
    busy = await repo.busy_intervals(day)
    return free_slots(day, service.duration_min, busy, config.now())


async def _render_dates(repo: BookingRepo, config: Config, service: Service, header: str = texts.CHOOSE_DATE) -> Tuple[str, InlineKeyboardMarkup]:
    days = await _dates_with_slots(repo, config, service)
    return (header if days else texts.NO_DATES), kb.dates(days)


async def _state_service(state: FSMContext) -> Optional[Service]:
    data = await state.get_data()
    return get_service(data.get("service", ""))


async def _state_day(state: FSMContext) -> Optional[date]:
    raw = (await state.get_data()).get("day", "")
    try:
        return datetime.strptime(raw, kb.DAY_FMT).date()
    except ValueError:
        return None


async def _render_my_bookings(repo: BookingRepo, config: Config, user_id: int) -> Tuple[str, Optional[InlineKeyboardMarkup]]:
    now = config.now()
    bookings = await repo.upcoming(now, now + MY_BOOKINGS_HORIZON, user_id=user_id)
    if not bookings:
        return texts.NO_BOOKINGS, None
    lines = "\n".join(texts.booking_line(b) for b in bookings)
    return f"<b>Ваши записи</b>\n\n{lines}", kb.my_bookings(bookings)


# ---- Начало и выбор услуги --------------------------------------------------

@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.WELCOME, reply_markup=kb.main_menu())


@router.message(F.text == texts.BTN_BOOK)
@router.message(Command("book"))
async def book(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.CHOOSE_SERVICE, reply_markup=kb.services())


# Кнопки меню объявлены раньше шагов «имя» и «телефон»: aiogram проверяет
# обработчики сверху вниз, и нажатие меню не должно приниматься за имя.
@router.message(F.text == texts.BTN_MY)
@router.message(Command("my"))
async def my_bookings(message: Message, state: FSMContext, repo: BookingRepo, config: Config) -> None:
    await state.clear()
    text, markup = await _render_my_bookings(repo, config, message.from_user.id)
    await message.answer(text, reply_markup=markup)


@router.callback_query(kb.NavCb.filter(F.to == "services"))
async def back_to_services(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _edit(callback, texts.CHOOSE_SERVICE, kb.services())
    await callback.answer()


@router.callback_query(kb.ServiceCb.filter())
async def choose_service(callback: CallbackQuery, callback_data: kb.ServiceCb, state: FSMContext, repo: BookingRepo, config: Config) -> None:
    service = get_service(callback_data.code)
    if service is None:
        await callback.answer(texts.SESSION_EXPIRED, show_alert=True)
        return
    await state.set_data({"service": service.code})
    await _edit(callback, *await _render_dates(repo, config, service))
    await callback.answer()


# ---- Выбор даты и времени ---------------------------------------------------

@router.callback_query(kb.NavCb.filter(F.to == "dates"))
async def back_to_dates(callback: CallbackQuery, state: FSMContext, repo: BookingRepo, config: Config) -> None:
    service = await _state_service(state)
    if service is None:
        await callback.answer(texts.SESSION_EXPIRED, show_alert=True)
        return
    await _edit(callback, *await _render_dates(repo, config, service))
    await callback.answer()


@router.callback_query(kb.DayCb.filter())
async def choose_day(callback: CallbackQuery, callback_data: kb.DayCb, state: FSMContext, repo: BookingRepo, config: Config) -> None:
    service = await _state_service(state)
    if service is None:
        await callback.answer(texts.SESSION_EXPIRED, show_alert=True)
        return
    day = datetime.strptime(callback_data.day, kb.DAY_FMT).date()
    slots = await _slots_for(repo, config, service, day)
    if not slots:
        # Пока клиент думал, день заняли — показываем даты заново.
        await _edit(callback, *await _render_dates(repo, config, service))
        await callback.answer(texts.DAY_FULL, show_alert=True)
        return
    await state.update_data(day=callback_data.day)
    await _edit(callback, f"Свободное время, {texts.format_day(day)}:", kb.slots(slots))
    await callback.answer()


@router.callback_query(kb.SlotCb.filter())
async def choose_slot(callback: CallbackQuery, callback_data: kb.SlotCb, state: FSMContext, repo: BookingRepo, config: Config) -> None:
    service = await _state_service(state)
    day = await _state_day(state)
    if service is None or day is None:
        await callback.answer(texts.SESSION_EXPIRED, show_alert=True)
        return
    starts_at = datetime.combine(day, datetime.strptime(callback_data.hhmm, kb.SLOT_FMT).time())
    slots = await _slots_for(repo, config, service, day)
    if starts_at not in slots:
        await _edit(callback, texts.SLOT_TAKEN, kb.slots(slots))
        await callback.answer()
        return
    await state.update_data(starts_at=starts_at.strftime(TIME_FMT))
    await state.set_state(BookingForm.name)
    await _edit(callback, f"{service.title}, {texts.format_moment(starts_at)}\n\n{texts.ASK_NAME}")
    await callback.answer()


# ---- Имя и телефон ----------------------------------------------------------

@router.message(BookingForm.name, F.text)
async def enter_name(message: Message, state: FSMContext) -> None:
    name = normalize_name(message.text)
    if name is None:
        await message.answer(texts.BAD_NAME)
        return
    await state.update_data(name=name)
    await state.set_state(BookingForm.phone)
    await message.answer(texts.ASK_PHONE, reply_markup=kb.phone_request())


@router.message(BookingForm.name)
async def enter_name_not_text(message: Message) -> None:
    await message.answer(texts.BAD_NAME)


@router.message(BookingForm.phone)
async def enter_phone(message: Message, state: FSMContext) -> None:
    raw = message.contact.phone_number if message.contact else (message.text or "")
    phone = normalize_phone(raw)
    if phone is None:
        await message.answer(texts.BAD_PHONE)
        return
    await state.update_data(phone=phone)
    await state.set_state(BookingForm.confirm)

    data = await state.get_data()
    service = get_service(data["service"])
    starts_at = datetime.strptime(data["starts_at"], TIME_FMT)
    # Первое сообщение убирает кнопку «Отправить номер» и возвращает меню.
    await message.answer(texts.ALMOST_DONE, reply_markup=kb.main_menu())
    await message.answer(
        texts.confirm_summary(service, starts_at, data["name"], phone),
        reply_markup=kb.confirm(),
    )


# ---- Подтверждение ----------------------------------------------------------

@router.callback_query(BookingForm.confirm, kb.ConfirmCb.filter(F.ok))
async def confirm_booking(callback: CallbackQuery, state: FSMContext, repo: BookingRepo, config: Config, bot: Bot) -> None:
    data = await state.get_data()
    service = get_service(data.get("service", ""))
    if service is None:
        await callback.answer(texts.SESSION_EXPIRED, show_alert=True)
        return
    starts_at = datetime.strptime(data["starts_at"], TIME_FMT)
    now = config.now()

    # Слот мог уйти в прошлое, пока клиент сидел на этом экране.
    still_free = starts_at in await _slots_for(repo, config, service, starts_at.date())
    new = NewBooking(
        user_id=callback.from_user.id,
        client_name=data["name"],
        phone=data["phone"],
        service_code=service.code,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=service.duration_min),
    )
    # Если до визита меньше, чем время напоминания, напоминать уже не нужно.
    skip_reminder = starts_at - now <= timedelta(minutes=REMINDER_BEFORE_MIN)
    booking_id = await repo.create(new, now, reminded=skip_reminder) if still_free else None

    if booking_id is None:
        await state.set_state(None)
        await state.set_data({"service": service.code})
        await _edit(callback, *await _render_dates(repo, config, service, header=texts.SLOT_TAKEN))
        await callback.answer()
        return

    await state.clear()
    await _edit(callback, texts.booking_done(service, starts_at))
    await callback.answer("Записали!")
    booking = await repo.get(booking_id)
    await notify_admins(bot, config.admin_ids, texts.admin_new_booking(booking))


@router.callback_query(kb.ConfirmCb.filter(~F.ok))
async def abort_booking(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _edit(callback, texts.BOOKING_ABORTED)
    await callback.answer()


@router.callback_query(kb.ConfirmCb.filter())
async def stale_confirm(callback: CallbackQuery) -> None:
    """Нажали «Подтвердить» на старом сообщении, когда запись уже не оформляется."""
    await callback.answer(texts.SESSION_EXPIRED, show_alert=True)


# ---- Отмена своей записи ----------------------------------------------------

@router.callback_query(kb.CancelCb.filter())
async def cancel_booking(callback: CallbackQuery, callback_data: kb.CancelCb, repo: BookingRepo, config: Config, bot: Bot) -> None:
    booking = await repo.cancel(callback_data.booking_id, user_id=callback.from_user.id)
    if booking is None:
        await callback.answer(texts.NOT_FOUND, show_alert=True)
        return
    await _edit(callback, *await _render_my_bookings(repo, config, callback.from_user.id))
    await callback.answer("Запись отменена")
    await notify_admins(bot, config.admin_ids, texts.admin_cancelled(booking))
