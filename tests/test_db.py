from datetime import date, datetime, timedelta

import pytest

from bot.db import BookingRepo, NewBooking

NOW = datetime(2026, 11, 23, 9, 0)
START = datetime(2026, 11, 23, 12, 0)


def make_booking(starts_at=START, minutes=60, user_id=1):
    return NewBooking(
        user_id=user_id,
        client_name="Тест",
        phone="+79000000000",
        service_code="haircut",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=minutes),
    )


@pytest.fixture
async def repo(tmp_path):
    repo = BookingRepo(str(tmp_path / "test.db"))
    await repo.init()
    return repo


async def test_created_booking_appears_in_busy_intervals(repo):
    assert await repo.create(make_booking(), NOW, reminded=False) is not None
    assert await repo.busy_intervals(date(2026, 11, 23)) == [(START, START + timedelta(hours=1))]
    assert await repo.busy_intervals(date(2026, 11, 24)) == []


async def test_overlapping_booking_is_refused(repo):
    await repo.create(make_booking(), NOW, reminded=False)
    overlapping = make_booking(starts_at=START + timedelta(minutes=30), user_id=2)
    assert await repo.create(overlapping, NOW, reminded=False) is None


async def test_client_can_cancel_only_own_booking_and_slot_frees_up(repo):
    booking_id = await repo.create(make_booking(user_id=1), NOW, reminded=False)
    assert await repo.cancel(booking_id, user_id=2) is None
    cancelled = await repo.cancel(booking_id, user_id=1)
    assert cancelled.id == booking_id
    assert await repo.cancel(booking_id, user_id=1) is None  # повторно нельзя
    assert await repo.busy_intervals(START.date()) == []


async def test_upcoming_filters_by_user_and_skips_cancelled(repo):
    first = await repo.create(make_booking(user_id=1), NOW, reminded=False)
    await repo.create(make_booking(starts_at=START + timedelta(hours=2), user_id=2), NOW, reminded=False)
    until = NOW + timedelta(days=1)
    assert [b.user_id for b in await repo.upcoming(NOW, until)] == [1, 2]
    assert [b.id for b in await repo.upcoming(NOW, until, user_id=1)] == [first]
    await repo.cancel(first)
    assert [b.user_id for b in await repo.upcoming(NOW, until)] == [2]


async def test_due_reminders_respect_window_and_reminded_flag(repo):
    soon = await repo.create(make_booking(starts_at=datetime(2026, 11, 23, 10, 30)), NOW, reminded=False)
    await repo.create(make_booking(starts_at=datetime(2026, 11, 23, 15, 0)), NOW, reminded=False)
    due = await repo.due_reminders(NOW, timedelta(hours=2))
    assert [b.id for b in due] == [soon]
    await repo.mark_reminded(soon)
    assert await repo.due_reminders(NOW, timedelta(hours=2)) == []
