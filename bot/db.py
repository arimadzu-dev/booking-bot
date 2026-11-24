"""Хранение записей в SQLite.

Всё время хранится как местное время мастера строкой «2026-11-25T14:30».
Строки такого формата сравниваются так же, как даты, поэтому поиск
пересечений можно делать прямо в SQL.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List, Optional

import aiosqlite

from bot.schedule import Interval

TIME_FMT = "%Y-%m-%dT%H:%M"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS bookings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    client_name  TEXT    NOT NULL,
    phone        TEXT    NOT NULL,
    service_code TEXT    NOT NULL,
    starts_at    TEXT    NOT NULL,
    ends_at      TEXT    NOT NULL,
    status       TEXT    NOT NULL DEFAULT 'active',  -- active | cancelled
    reminded     INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bookings_starts ON bookings(starts_at);
"""

_COLUMNS = "id, user_id, client_name, phone, service_code, starts_at, ends_at, status"


@dataclass(frozen=True)
class Booking:
    id: int
    user_id: int
    client_name: str
    phone: str
    service_code: str
    starts_at: datetime
    ends_at: datetime
    status: str


@dataclass(frozen=True)
class NewBooking:
    user_id: int
    client_name: str
    phone: str
    service_code: str
    starts_at: datetime
    ends_at: datetime


def _fmt(moment: datetime) -> str:
    return moment.strftime(TIME_FMT)


def _parse(text: str) -> datetime:
    return datetime.strptime(text, TIME_FMT)


def _row_to_booking(row: aiosqlite.Row) -> Booking:
    return Booking(
        id=row[0],
        user_id=row[1],
        client_name=row[2],
        phone=row[3],
        service_code=row[4],
        starts_at=_parse(row[5]),
        ends_at=_parse(row[6]),
        status=row[7],
    )


class BookingRepo:
    """Все операции с записями. Обработчики не пишут SQL сами."""

    def __init__(self, path: str) -> None:
        self._path = path

    async def init(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()

    async def busy_intervals(self, day: date) -> List[Interval]:
        start = datetime.combine(day, datetime.min.time())
        end = start + timedelta(days=1)
        async with aiosqlite.connect(self._path) as db:
            cursor = await db.execute(
                "SELECT starts_at, ends_at FROM bookings "
                "WHERE status = 'active' AND starts_at < ? AND ends_at > ?",
                (_fmt(end), _fmt(start)),
            )
            rows = await cursor.fetchall()
        return [(_parse(a), _parse(b)) for a, b in rows]

    async def create(self, new: NewBooking, now: datetime, reminded: bool) -> Optional[int]:
        """Создаёт запись. Возвращает None, если время уже кто-то занял.

        BEGIN IMMEDIATE блокирует базу на запись, поэтому два клиента,
        нажавшие «Подтвердить» одновременно, не попадут на один слот.
        """
        async with aiosqlite.connect(self._path) as db:
            await db.execute("BEGIN IMMEDIATE")
            cursor = await db.execute(
                "SELECT 1 FROM bookings WHERE status = 'active' "
                "AND starts_at < ? AND ends_at > ? LIMIT 1",
                (_fmt(new.ends_at), _fmt(new.starts_at)),
            )
            if await cursor.fetchone():
                await db.rollback()
                return None
            cursor = await db.execute(
                "INSERT INTO bookings (user_id, client_name, phone, service_code, "
                "starts_at, ends_at, reminded, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new.user_id,
                    new.client_name,
                    new.phone,
                    new.service_code,
                    _fmt(new.starts_at),
                    _fmt(new.ends_at),
                    int(reminded),
                    _fmt(now),
                ),
            )
            await db.commit()
            return cursor.lastrowid

    async def get(self, booking_id: int) -> Optional[Booking]:
        async with aiosqlite.connect(self._path) as db:
            cursor = await db.execute(
                f"SELECT {_COLUMNS} FROM bookings WHERE id = ?", (booking_id,)
            )
            row = await cursor.fetchone()
        return _row_to_booking(row) if row else None

    async def upcoming(
        self, now: datetime, until: datetime, user_id: Optional[int] = None
    ) -> List[Booking]:
        """Активные записи в промежутке [now, until). Можно отфильтровать по клиенту."""
        query = (
            f"SELECT {_COLUMNS} FROM bookings "
            "WHERE status = 'active' AND starts_at >= ? AND starts_at < ?"
        )
        params: list = [_fmt(now), _fmt(until)]
        if user_id is not None:
            query += " AND user_id = ?"
            params.append(user_id)
        query += " ORDER BY starts_at"
        async with aiosqlite.connect(self._path) as db:
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
        return [_row_to_booking(r) for r in rows]

    async def cancel(self, booking_id: int, user_id: Optional[int] = None) -> Optional[Booking]:
        """Отменяет запись. Если передан user_id — только запись этого клиента.

        Возвращает отменённую запись или None, если отменять нечего.
        """
        booking = await self.get(booking_id)
        if booking is None or booking.status != "active":
            return None
        if user_id is not None and booking.user_id != user_id:
            return None
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "UPDATE bookings SET status = 'cancelled' WHERE id = ?", (booking_id,)
            )
            await db.commit()
        return booking

    async def due_reminders(self, now: datetime, ahead: timedelta) -> List[Booking]:
        """Записи, которые начнутся в ближайшее время и о которых ещё не напомнили."""
        async with aiosqlite.connect(self._path) as db:
            cursor = await db.execute(
                f"SELECT {_COLUMNS} FROM bookings WHERE status = 'active' "
                "AND reminded = 0 AND starts_at > ? AND starts_at <= ?",
                (_fmt(now), _fmt(now + ahead)),
            )
            rows = await cursor.fetchall()
        return [_row_to_booking(r) for r in rows]

    async def mark_reminded(self, booking_id: int) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute("UPDATE bookings SET reminded = 1 WHERE id = ?", (booking_id,))
            await db.commit()
