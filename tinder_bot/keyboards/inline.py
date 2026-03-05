from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def browse_kb(user_id: int) -> InlineKeyboardMarkup:
    """
    Кнопки под анкетой.
    user_id — это ID анкеты, которую показываем (to_user_id для лайка).
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="❤️ Лайк", callback_data=f"like:{user_id}"),
                InlineKeyboardButton(text="⏭️ Пропустить", callback_data=f"dislike:{user_id}"),
            ]
        ]
    )


def required_subscription_kb(channels: list[str], labels: dict[str, str] | None = None) -> InlineKeyboardMarkup:
    """
    Клавиатура для обязательной подписки:
    - кнопки-ссылки на каналы (если указаны как username)
    - кнопка "Проверить подписку"
    """
    rows: list[list[InlineKeyboardButton]] = []

    for idx, ch in enumerate(channels):
        c = (ch or "").strip()
        if not c:
            continue
        # Ссылку корректно строим только для username каналов
        if c.lstrip("@").replace("_", "").isalnum():
            username = c[1:] if c.startswith("@") else c
            # Если передали labels (например, для "только недостающих" каналов) — используем их.
            btn_text = (labels or {}).get(ch)
            if not btn_text:
                # Специальные подписи по порядку (fallback)
                if idx == 0:
                    btn_text = "Подписаться на Startup club"
                elif idx == 1:
                    btn_text = "Подписаться на Предпринимательский клуб"
                elif idx == 2:
                    btn_text = "Подписаться на основателя клуба"
                else:
                    btn_text = f"Подписаться: @{username}"
            rows.append([InlineKeyboardButton(text=btn_text, url=f"https://t.me/{username}")])
        else:
            # Для ID/ссылок просто показываем текстом не получится — оставим только проверку
            pass

    rows.append([InlineKeyboardButton(text="✅ Проверить подписку", callback_data="subcheck")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def consent_kb() -> InlineKeyboardMarkup:
    """
    Клавиатура для согласия на обработку персональных данных.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Согласен", callback_data="consent:yes"),
                InlineKeyboardButton(text="❌ Не согласен", callback_data="consent:no"),
            ]
        ]
    )
    