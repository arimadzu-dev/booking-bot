"""Проверка того, что вводит пользователь."""
from __future__ import annotations

import re
from typing import Optional

MAX_NAME_LEN = 50
_PHONE_JUNK = re.compile(r"[\s()\-]")


def normalize_name(text: str) -> Optional[str]:
    """Имя без лишних пробелов или None, если оно пустое/слишком длинное."""
    name = " ".join(text.split())
    if not name or len(name) > MAX_NAME_LEN:
        return None
    return name


def normalize_phone(text: str) -> Optional[str]:
    """Приводит российский номер к виду +7XXXXXXXXXX, иначе None.

    Принимает «8 (900) 123-45-67», «+7 900 1234567», «9001234567».
    """
    digits = _PHONE_JUNK.sub("", text.strip())
    if digits.startswith("+"):
        digits = digits[1:]
    if not digits.isdigit():
        return None
    if len(digits) == 10:
        digits = "7" + digits
    if len(digits) == 11 and digits[0] in "78":
        return "+7" + digits[1:]
    return None
