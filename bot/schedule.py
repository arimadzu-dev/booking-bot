"""Услуги, рабочие часы и расчёт свободных слотов.

Здесь нет ничего про Telegram и базу данных — только «чистая» логика,
поэтому её легко тестировать. Под нового заказчика обычно меняются
только константы в начале файла.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class Service:
    code: str  # короткий латинский идентификатор, уходит в callback-кнопки
    title: str
    duration_min: int
    price: int  # в валюте CURRENCY


# ---- Настройки под конкретного мастера -------------------------------------
CURRENCY = "₸"
SERVICES: Tuple[Service, ...] = (
    Service("haircut", "Мужская стрижка", 60, 5000),
    Service("beard", "Оформление бороды", 30, 3000),
    Service("combo", "Стрижка + борода", 90, 7000),
)
WORK_START = time(10, 0)
WORK_END = time(20, 0)
DAYS_OFF = frozenset({6})  # 0 = понедельник ... 6 = воскресенье
SLOT_STEP_MIN = 30  # шаг сетки времени
BOOKING_HORIZON_DAYS = 14  # на сколько дней вперёд открыта запись
MIN_LEAD_MIN = 60  # нельзя записаться ближе чем за час до начала
REMINDER_BEFORE_MIN = 120  # за сколько минут напомнить клиенту
# -----------------------------------------------------------------------------

Interval = Tuple[datetime, datetime]


def get_service(code: str) -> Optional[Service]:
    return next((s for s in SERVICES if s.code == code), None)


def candidate_dates(today: date) -> List[date]:
    """Рабочие дни в пределах горизонта записи, начиная с сегодняшнего."""
    days = (today + timedelta(days=i) for i in range(BOOKING_HORIZON_DAYS))
    return [d for d in days if d.weekday() not in DAYS_OFF]


def _overlaps(start: datetime, end: datetime, busy: Iterable[Interval]) -> bool:
    # Два интервала пересекаются, если каждый начинается раньше конца другого.
    return any(start < b_end and b_start < end for b_start, b_end in busy)


def free_slots(
    day: date, duration_min: int, busy: Iterable[Interval], now: datetime
) -> List[datetime]:
    """Время начала, на которое ещё можно записаться на услугу.

    busy — занятые интервалы этого дня, now — текущее местное время.
    """
    busy = list(busy)
    duration = timedelta(minutes=duration_min)
    step = timedelta(minutes=SLOT_STEP_MIN)
    earliest = now + timedelta(minutes=MIN_LEAD_MIN)
    day_end = datetime.combine(day, WORK_END)

    slots = []
    current = datetime.combine(day, WORK_START)
    while current + duration <= day_end:
        if current >= earliest and not _overlaps(current, current + duration, busy):
            slots.append(current)
        current += step
    return slots
