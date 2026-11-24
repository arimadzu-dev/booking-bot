"""Фоновая задача: раз в минуту ищет записи, о которых пора напомнить."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from aiogram import Bot

from bot import texts
from bot.config import Config
from bot.db import BookingRepo
from bot.notify import safe_send
from bot.schedule import REMINDER_BEFORE_MIN

log = logging.getLogger(__name__)
CHECK_INTERVAL_SEC = 60


async def send_due_reminders(bot: Bot, repo: BookingRepo, config: Config) -> int:
    """Один проход: отправляет напоминания и возвращает, сколько отправлено."""
    ahead = timedelta(minutes=REMINDER_BEFORE_MIN)
    sent = 0
    for booking in await repo.due_reminders(config.now(), ahead):
        if await safe_send(bot, booking.user_id, texts.reminder(booking)):
            sent += 1
        # Отмечаем даже при ошибке доставки, иначе бот будет стучаться каждую минуту.
        await repo.mark_reminded(booking.id)
    return sent


async def run_reminders(bot: Bot, repo: BookingRepo, config: Config) -> None:
    while True:
        try:
            await send_due_reminders(bot, repo, config)
        except Exception:  # цикл не должен умереть из-за одной ошибки
            log.exception("Ошибка при рассылке напоминаний")
        await asyncio.sleep(CHECK_INTERVAL_SEC)
