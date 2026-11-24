import pytest

from bot.validators import normalize_name, normalize_phone


@pytest.mark.parametrize(
    "raw",
    ["+7 900 123-45-67", "8 (900) 123-45-67", "89001234567", "79001234567", "9001234567"],
)
def test_russian_phone_formats_normalize_to_plus7(raw):
    assert normalize_phone(raw) == "+79001234567"


@pytest.mark.parametrize("raw", ["", "123", "abc", "+1 555 123 4567", "8900123456789"])
def test_invalid_phones_are_rejected(raw):
    assert normalize_phone(raw) is None


def test_name_is_trimmed_and_length_limited():
    assert normalize_name("  Иван   Петров ") == "Иван Петров"
    assert normalize_name("   ") is None
    assert normalize_name("я" * 51) is None
