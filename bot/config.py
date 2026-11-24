"""Настройки из файла .env (токен, админы, часовой пояс)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import FrozenSet
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: FrozenSet[int]
    timezone: ZoneInfo
    db_path: str

    def now(self) -> datetime:
        """Текущее время мастера без часового пояса — так оно хранится в базе."""
        return datetime.now(self.timezone).replace(tzinfo=None, second=0, microsecond=0)


def _parse_admin_ids(raw: str) -> FrozenSet[int]:
    try:
        ids = frozenset(int(part) for part in raw.split(",") if part.strip())
    except ValueError as exc:
        raise ConfigError("ADMIN_IDS — это числа через запятую, например 123456,789012") from exc
    if not ids:
        raise ConfigError("ADMIN_IDS пуст. Узнать свой id можно у бота @userinfobot")
    return ids


def load_config() -> Config:
    load_dotenv()
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise ConfigError("BOT_TOKEN не задан. Скопируйте .env.example в .env и вставьте токен от @BotFather")

    tz_name = os.getenv("TIMEZONE", "Europe/Moscow")
    try:
        timezone = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as exc:
        raise ConfigError(f"Неизвестный часовой пояс TIMEZONE={tz_name}") from exc

    return Config(
        bot_token=token,
        admin_ids=_parse_admin_ids(os.getenv("ADMIN_IDS", "")),
        timezone=timezone,
        db_path=os.getenv("DB_PATH", "bookings.db"),
    )
