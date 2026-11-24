"""Команды мастера: /admin — записи на неделю с кнопками отмены."""
from __future__ import annotations

from datetime import timedelta
from typing import FrozenSet, Optional, Tuple

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot import keyboards as kb
from bot import texts
from bot.config import Config
from bot.db import BookingRepo
from bot.handlers.common import edit_message as _edit
from bot.notify import safe_send

ADMIN_HORIZON = timedelta(days=7)


async def _render(repo: BookingRepo, config: Config) -> Tuple[str, Optional[InlineKeyboardMarkup]]:
    now = config.now()
    bookings = await repo.upcoming(now, now + ADMIN_HORIZON)
    if not bookings:
        return "На ближайшую неделю записей нет.", None
    lines = "\n".join(texts.booking_line(b, with_client=True) for b in bookings)
    return f"<b>Записи на 7 дней</b>\n\n{lines}\n\nНажмите на запись, чтобы отменить её.", kb.admin_bookings(bookings)


async def show_bookings(message: Message, repo: BookingRepo, config: Config) -> None:
    text, markup = await _render(repo, config)
    await message.answer(text, reply_markup=markup)


async def cancel_booking(callback: CallbackQuery, callback_data: kb.AdminCancelCb, repo: BookingRepo, config: Config, bot: Bot) -> None:
    booking = await repo.cancel(callback_data.booking_id)
    if booking is None:
        await callback.answer(texts.NOT_FOUND, show_alert=True)
        return
    delivered = await safe_send(bot, booking.user_id, texts.client_cancelled_by_master(booking))
    await _edit(callback, *await _render(repo, config))
    note = "Отменено, клиент уведомлён" if delivered else "Отменено, но клиент заблокировал бота — позвоните ему"
    await callback.answer(note, show_alert=not delivered)


def build_admin_router(admin_ids: FrozenSet[int]) -> Router:
    """Роутер срабатывает только для id из ADMIN_IDS, остальных пропускает дальше."""
    router = Router(name="admin")
    router.message.filter(F.from_user.id.in_(admin_ids))
    router.callback_query.filter(F.from_user.id.in_(admin_ids))
    router.message.register(show_bookings, Command("admin"))
    router.callback_query.register(cancel_booking, kb.AdminCancelCb.filter())
    return router
