from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    """Текущая дата/время в UTC (timezone-aware)."""
    return datetime.now(timezone.utc)


def format_contact(telegram_id: int, username: str | None) -> str:
    """
    Формат контакта: если есть username -> @username, иначе tg://user?id=...
    """
    if username:
        if username.startswith("@"):
            return username
        return f"@{username}"
    return f"tg://user?id={telegram_id}"
