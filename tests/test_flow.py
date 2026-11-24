"""Сквозной тест: апдейты идут через настоящий Dispatcher, а Telegram подменён.

FakeSession записывает всё, что бот «отправил», вместо реальных запросов.
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from aiogram.types import Message, Update

from bot import keyboards as kb
from bot import texts
from bot.config import Config
from bot.db import BookingRepo
from bot.handlers import client
from bot.handlers.admin import build_admin_router
from bot.reminders import send_due_reminders

ADMIN_ID = 100
ALICE = 1
BOB = 2
FIXED_NOW = datetime(2026, 11, 23, 9, 0)  # понедельник, до открытия
DAY = date(2026, 11, 24)


class FixedConfig(Config):
    """Конфиг с замороженным временем, чтобы тест не зависел от часов."""

    def now(self) -> datetime:
        return self._now if hasattr(self, "_now") else FIXED_NOW


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls = []

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, AnswerCallbackQuery):
            return True
        chat_id = getattr(method, "chat_id", None) or ALICE
        payload = {
            "message_id": len(self.calls),
            "date": 0,
            "chat": {"id": chat_id, "type": "private"},
            "text": getattr(method, "text", ""),
        }
        return Message.model_validate(payload, context={"bot": bot})

    async def stream_content(self, *args, **kwargs):  # pragma: no cover - не используется
        yield b""

    async def close(self) -> None:
        pass

    def texts_to(self, chat_id: int):
        return [c.text for c in self.calls if isinstance(c, SendMessage) and c.chat_id == chat_id]

    def last_text(self) -> str:
        for call in reversed(self.calls):
            if isinstance(call, (SendMessage, EditMessageText)):
                return call.text
        return ""

    def alerts(self):
        return [c.text for c in self.calls if isinstance(c, AnswerCallbackQuery) and c.text]


class Harness:
    def __init__(self, repo: BookingRepo, config: Config) -> None:
        self.session = FakeSession()
        self.bot = Bot("42:TEST", session=self.session)
        self.dp = Dispatcher(storage=MemoryStorage(), repo=repo, config=config)
        self.dp.include_router(build_admin_router(config.admin_ids))
        self.dp.include_router(client.router)
        self._update_id = 0

    async def _feed(self, payload: dict) -> None:
        self._update_id += 1
        update = Update.model_validate({"update_id": self._update_id, **payload}, context={"bot": self.bot})
        await self.dp.feed_update(self.bot, update)

    @staticmethod
    def _user(user_id: int) -> dict:
        return {"id": user_id, "is_bot": False, "first_name": f"u{user_id}"}

    async def text(self, user_id: int, text: str) -> None:
        await self._feed({"message": {
            "message_id": 1, "date": 0, "text": text,
            "chat": {"id": user_id, "type": "private"}, "from": self._user(user_id),
        }})

    async def press(self, user_id: int, data: str) -> None:
        await self._feed({"callback_query": {
            "id": str(self._update_id), "chat_instance": "ci", "data": data,
            "from": self._user(user_id),
            "message": {"message_id": 1, "date": 0, "text": "x", "chat": {"id": user_id, "type": "private"}},
        }})

    async def book(self, user_id: int, hhmm: str, name: str = "Иван", phone: str = "8 900 123 45 67") -> None:
        await self.text(user_id, texts.BTN_BOOK)
        await self.press(user_id, kb.ServiceCb(code="haircut").pack())
        await self.press(user_id, kb.DayCb(day=DAY.strftime(kb.DAY_FMT)).pack())
        await self.press(user_id, kb.SlotCb(hhmm=hhmm).pack())
        await self.text(user_id, name)
        await self.text(user_id, phone)
        await self.press(user_id, kb.ConfirmCb(ok=True).pack())


@pytest.fixture
async def env(tmp_path):
    config = FixedConfig(
        bot_token="42:TEST",
        admin_ids=frozenset({ADMIN_ID}),
        timezone=ZoneInfo("Europe/Moscow"),
        db_path=str(tmp_path / "flow.db"),
    )
    repo = BookingRepo(config.db_path)
    await repo.init()
    yield Harness(repo, config), repo
    # В боте роутер подключается один раз, а в тестах — к новому диспетчеру
    # на каждый тест. Публичного способа отцепить роутер в aiogram нет.
    client.router._parent_router = None


async def test_full_booking_flow_saves_booking_and_notifies_master(env):
    h, repo = env
    await h.text(ALICE, "/start")
    assert h.session.last_text() == texts.WELCOME

    await h.book(ALICE, "1000")

    bookings = await repo.upcoming(FIXED_NOW, datetime(2026, 12, 31))
    assert len(bookings) == 1
    assert bookings[0].phone == "+79001234567"
    assert bookings[0].starts_at == datetime(2026, 11, 24, 10, 0)
    edits = [c.text for c in h.session.calls if isinstance(c, EditMessageText)]
    assert "Готово" in edits[-1]
    assert any("Новая запись" in t for t in h.session.texts_to(ADMIN_ID))


async def test_second_client_cannot_take_occupied_slot(env):
    h, repo = env
    await h.book(ALICE, "1000")
    await h.text(BOB, texts.BTN_BOOK)
    await h.press(BOB, kb.ServiceCb(code="haircut").pack())
    await h.press(BOB, kb.DayCb(day=DAY.strftime(kb.DAY_FMT)).pack())
    await h.press(BOB, kb.SlotCb(hhmm="1030").pack())  # пересекается с 10:00–11:00
    assert h.session.last_text() == texts.SLOT_TAKEN
    assert len(await repo.upcoming(FIXED_NOW, datetime(2026, 12, 31))) == 1


async def test_menu_button_during_name_step_is_not_taken_as_name(env):
    h, _ = env
    await h.text(ALICE, texts.BTN_BOOK)
    await h.press(ALICE, kb.ServiceCb(code="haircut").pack())
    await h.press(ALICE, kb.DayCb(day=DAY.strftime(kb.DAY_FMT)).pack())
    await h.press(ALICE, kb.SlotCb(hhmm="1000").pack())
    await h.text(ALICE, texts.BTN_MY)
    assert h.session.last_text() == texts.NO_BOOKINGS


async def test_invalid_phone_is_asked_again(env):
    h, _ = env
    await h.text(ALICE, texts.BTN_BOOK)
    await h.press(ALICE, kb.ServiceCb(code="haircut").pack())
    await h.press(ALICE, kb.DayCb(day=DAY.strftime(kb.DAY_FMT)).pack())
    await h.press(ALICE, kb.SlotCb(hhmm="1000").pack())
    await h.text(ALICE, "Иван")
    await h.text(ALICE, "12345")
    assert h.session.last_text() == texts.BAD_PHONE


async def test_client_cancels_own_booking_and_master_is_told(env):
    h, repo = env
    await h.book(ALICE, "1000")
    booking = (await repo.upcoming(FIXED_NOW, datetime(2026, 12, 31)))[0]
    await h.text(ALICE, texts.BTN_MY)
    await h.press(ALICE, kb.CancelCb(booking_id=booking.id).pack())
    assert await repo.upcoming(FIXED_NOW, datetime(2026, 12, 31)) == []
    assert any("отменил" in t for t in h.session.texts_to(ADMIN_ID))


async def test_stranger_cannot_cancel_someone_elses_booking(env):
    h, repo = env
    await h.book(ALICE, "1000")
    booking = (await repo.upcoming(FIXED_NOW, datetime(2026, 12, 31)))[0]
    await h.press(BOB, kb.CancelCb(booking_id=booking.id).pack())
    await h.press(BOB, kb.AdminCancelCb(booking_id=booking.id).pack())  # и под видом админа
    assert len(await repo.upcoming(FIXED_NOW, datetime(2026, 12, 31))) == 1


async def test_admin_sees_bookings_and_cancel_notifies_client(env):
    h, repo = env
    await h.book(ALICE, "1000")
    booking = (await repo.upcoming(FIXED_NOW, datetime(2026, 12, 31)))[0]

    await h.text(ADMIN_ID, "/admin")
    assert "Иван" in h.session.last_text() and "+79001234567" in h.session.last_text()

    await h.press(ADMIN_ID, kb.AdminCancelCb(booking_id=booking.id).pack())
    assert await repo.upcoming(FIXED_NOW, datetime(2026, 12, 31)) == []
    assert any("мастер отменил" in t for t in h.session.texts_to(ALICE))


async def test_non_admin_admin_command_does_nothing(env):
    h, _ = env
    await h.text(BOB, "/admin")
    assert h.session.texts_to(BOB) == []


async def test_reminder_is_sent_once_before_visit(env):
    h, repo = env
    await h.book(ALICE, "1000")
    config = h.dp["config"]
    object.__setattr__(config, "_now", datetime(2026, 11, 24, 8, 30))  # за 1,5 часа

    assert await send_due_reminders(h.bot, repo, config) == 1
    assert await send_due_reminders(h.bot, repo, config) == 0
    assert any("Напоминаем" in t for t in h.session.texts_to(ALICE))
