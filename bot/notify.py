"""Отправка сообщений, которые не являются ответом на действие пользователя."""
from __future__ import annotations

import logging
from typing import Iterable

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

log = logging.getLogger(__name__)


async def safe_send(bot: Bot, chat_id: int, text: str) -> bool:
    """Отправляет сообщение и не роняет бота, если получатель его заблокировал."""
    try:
        await bot.send_message(chat_id, text)
        return True
    except TelegramAPIError as exc:
        log.warning("Не удалось отправить сообщение в чат %s: %s", chat_id, exc)
        return False


async def notify_admins(bot: Bot, admin_ids: Iterable[int], text: str) -> None:
    for admin_id in admin_ids:
        await safe_send(bot, admin_id, text)
