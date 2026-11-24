"""Кнопки и данные, которые они передают боту при нажатии (callback data)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, List

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import texts
from bot.db import Booking
from bot.schedule import SERVICES


# Каждый класс — тип нажатия. aiogram сам упакует поля в строку
# вида «day:20261125» и распакует обратно в обработчике.
class ServiceCb(CallbackData, prefix="svc"):
    code: str


class DayCb(CallbackData, prefix="day"):
    day: str  # ГГГГММДД


class SlotCb(CallbackData, prefix="slot"):
    hhmm: str  # ЧЧММ — без двоеточия, оно служебное у aiogram


class NavCb(CallbackData, prefix="nav"):
    to: str  # services | dates


class ConfirmCb(CallbackData, prefix="confirm"):
    ok: bool


class CancelCb(CallbackData, prefix="cancel"):
    booking_id: int


class AdminCancelCb(CallbackData, prefix="acancel"):
    booking_id: int


DAY_FMT = "%Y%m%d"
SLOT_FMT = "%H%M"


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=texts.BTN_BOOK), KeyboardButton(text=texts.BTN_MY)]],
        resize_keyboard=True,
    )


def phone_request() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=texts.BTN_SEND_PHONE, request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def services() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for service in SERVICES:
        builder.button(text=texts.service_button(service), callback_data=ServiceCb(code=service.code))
    builder.adjust(1)
    return builder.as_markup()


def dates(days: Iterable[date]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for day in days:
        builder.button(text=texts.format_day(day), callback_data=DayCb(day=day.strftime(DAY_FMT)))
    builder.adjust(3)
    builder.row(_back("« К услугам", "services"))
    return builder.as_markup()


def slots(moments: Iterable[datetime]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for moment in moments:
        builder.button(text=f"{moment:%H:%M}", callback_data=SlotCb(hhmm=moment.strftime(SLOT_FMT)))
    builder.adjust(4)
    builder.row(_back("« К датам", "dates"))
    return builder.as_markup()


def confirm() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data=ConfirmCb(ok=True))
    builder.button(text="✖ Отмена", callback_data=ConfirmCb(ok=False))
    return builder.as_markup()


def my_bookings(bookings: List[Booking]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for booking in bookings:
        builder.button(
            text=f"Отменить {booking.starts_at:%d.%m %H:%M}",
            callback_data=CancelCb(booking_id=booking.id),
        )
    builder.adjust(1)
    return builder.as_markup()


def admin_bookings(bookings: List[Booking]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for booking in bookings:
        builder.button(
            text=f"✖ {booking.starts_at:%d.%m %H:%M} {booking.client_name}",
            callback_data=AdminCancelCb(booking_id=booking.id),
        )
    builder.adjust(1)
    return builder.as_markup()


def _back(text: str, to: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=NavCb(to=to).pack())
