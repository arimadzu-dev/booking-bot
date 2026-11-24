"""Все тексты и форматирование. Тон общения меняется здесь, а не в обработчиках."""
from __future__ import annotations

from datetime import date, datetime
from html import escape

from bot.db import Booking
from bot.schedule import CURRENCY, Service, get_service

WEEKDAYS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")

BTN_BOOK = "📅 Записаться"
BTN_MY = "🗂 Мои записи"
BTN_SEND_PHONE = "📱 Отправить номер"

WELCOME = (
    "Здравствуйте! Я помогу записаться к мастеру.\n\n"
    "Нажмите «Записаться», чтобы выбрать услугу и время."
)
CHOOSE_SERVICE = "Выберите услугу:"
CHOOSE_DATE = "Выберите дату:"
NO_DATES = "К сожалению, в ближайшие две недели свободного времени нет."
DAY_FULL = "На этот день всё занято, выберите другой."
SLOT_TAKEN = "Это время только что заняли. Выберите другое:"
ASK_NAME = "Как к вам обращаться?"
BAD_NAME = "Напишите, пожалуйста, имя (до 50 символов)."
ASK_PHONE = "Оставьте номер телефона — нажмите кнопку ниже или напишите его."
BAD_PHONE = "Не получилось распознать номер. Пример: +7 900 123-45-67"
ALMOST_DONE = "Почти готово!"
BOOKING_ABORTED = "Запись отменена. Если передумаете — нажмите «Записаться»."
NO_BOOKINGS = "У вас нет предстоящих записей."
NOT_FOUND = "Запись не найдена или уже отменена."
SESSION_EXPIRED = "Сессия устарела, начните запись заново."
CONSENT = (
    "<i>Нажимая «Подтвердить», вы соглашаетесь на обработку имени и номера "
    "телефона для записи и напоминаний.</i>"
)


def format_day(day: date) -> str:
    return f"{WEEKDAYS[day.weekday()]}, {day:%d.%m}"


def format_moment(moment: datetime) -> str:
    return f"{format_day(moment.date())} в {moment:%H:%M}"


def service_title(code: str) -> str:
    service = get_service(code)
    return service.title if service else code


def format_price(amount: int) -> str:
    """5000 → «5 000 ₸»: пробел между тысячами, как принято в РК и РФ."""
    return f"{amount:,}".replace(",", " ") + f" {CURRENCY}"


def service_button(service: Service) -> str:
    return f"{service.title} · {service.duration_min} мин · {format_price(service.price)}"


def confirm_summary(service: Service, starts_at: datetime, name: str, phone: str) -> str:
    return (
        "<b>Проверьте запись</b>\n\n"
        f"Услуга: {escape(service.title)} ({format_price(service.price)})\n"
        f"Когда: {format_moment(starts_at)}\n"
        f"Имя: {escape(name)}\n"
        f"Телефон: {phone}\n\n"
        f"{CONSENT}"
    )


def booking_done(service: Service, starts_at: datetime) -> str:
    return (
        f"✅ Готово! Вы записаны на «{escape(service.title)}» {format_moment(starts_at)}.\n"
        "Я напомню заранее. Отменить запись можно в разделе «Мои записи»."
    )


def booking_line(booking: Booking, with_client: bool = False) -> str:
    line = f"{format_moment(booking.starts_at)} — {escape(service_title(booking.service_code))}"
    if with_client:
        line += f"\n    {escape(booking.client_name)}, {booking.phone}"
    return line


def admin_new_booking(booking: Booking) -> str:
    return "🆕 <b>Новая запись</b>\n" + booking_line(booking, with_client=True)


def admin_cancelled(booking: Booking) -> str:
    return "❌ <b>Клиент отменил запись</b>\n" + booking_line(booking, with_client=True)


def client_cancelled_by_master(booking: Booking) -> str:
    return (
        f"К сожалению, мастер отменил вашу запись {format_moment(booking.starts_at)}.\n"
        "Выберите другое время через «Записаться»."
    )


def reminder(booking: Booking) -> str:
    return (
        f"⏰ Напоминаем о записи: {format_moment(booking.starts_at)} — "
        f"«{escape(service_title(booking.service_code))}». Ждём вас!"
    )
