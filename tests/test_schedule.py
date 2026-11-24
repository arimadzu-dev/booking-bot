from datetime import date, datetime, timedelta

from bot import schedule
from bot.schedule import candidate_dates, free_slots, get_service

MONDAY = date(2026, 11, 23)
EARLY = datetime(2026, 11, 22, 9, 0)  # заведомо раньше рабочего дня


def test_get_service_returns_known_service_and_none_for_unknown():
    assert get_service("haircut").duration_min == 60
    assert get_service("nope") is None


def test_candidate_dates_skip_days_off_and_respect_horizon():
    days = candidate_dates(MONDAY)
    assert all(d.weekday() not in schedule.DAYS_OFF for d in days)
    assert days[0] == MONDAY
    assert max(days) < MONDAY + timedelta(days=schedule.BOOKING_HORIZON_DAYS)


def test_empty_day_has_slots_from_open_until_service_fits():
    slots = free_slots(MONDAY, 60, [], EARLY)
    assert slots[0] == datetime(2026, 11, 23, 10, 0)
    assert slots[-1] == datetime(2026, 11, 23, 19, 0)  # 19:00 + 60 мин = закрытие


def test_busy_interval_blocks_overlapping_starts_but_not_adjacent():
    busy = [(datetime(2026, 11, 23, 12, 0), datetime(2026, 11, 23, 13, 0))]
    slots = free_slots(MONDAY, 60, busy, EARLY)
    assert datetime(2026, 11, 23, 11, 0) in slots  # заканчивается ровно в 12:00
    assert datetime(2026, 11, 23, 11, 30) not in slots  # залезает на 12:00
    assert datetime(2026, 11, 23, 12, 30) not in slots
    assert datetime(2026, 11, 23, 13, 0) in slots


def test_slots_closer_than_min_lead_are_hidden():
    now = datetime(2026, 11, 23, 12, 10)
    slots = free_slots(MONDAY, 30, [], now)
    assert slots[0] == datetime(2026, 11, 23, 13, 30)  # 13:00 ближе чем за час


def test_fully_booked_day_has_no_slots():
    busy = [(datetime(2026, 11, 23, 10, 0), datetime(2026, 11, 23, 20, 0))]
    assert free_slots(MONDAY, 30, busy, EARLY) == []


def test_price_is_formatted_with_thousands_and_currency():
    from bot.texts import format_price

    assert format_price(5000) == f"5 000 {schedule.CURRENCY}"
    assert format_price(800) == f"800 {schedule.CURRENCY}"
