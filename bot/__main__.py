"""Запуск: python -m bot"""
from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import ConfigError, load_config
from bot.db import BookingRepo
from bot.handlers import client
from bot.handlers.admin import build_admin_router
from bot.reminders import run_reminders


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        config = load_config()
    except ConfigError as exc:
        sys.exit(f"Ошибка настройки: {exc}")

    repo = BookingRepo(config.db_path)
    await repo.init()

    bot = Bot(config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    # MemoryStorage держит незавершённые записи в памяти: после перезапуска
    # клиенту придётся начать заново. Для большого потока — RedisStorage.
    dp = Dispatcher(storage=MemoryStorage(), repo=repo, config=config)
    dp.include_router(build_admin_router(config.admin_ids))  # админ раньше клиента
    dp.include_router(client.router)

    reminders = asyncio.create_task(run_reminders(bot, repo, config))
    try:
        await dp.start_polling(bot)
    finally:
        reminders.cancel()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
