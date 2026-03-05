from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📌 Моя анкета (/profile)")],
            [KeyboardButton(text="🔥 Смотреть анкеты (/browse)")],
            [KeyboardButton(text="🎉 Мэтчи (/matches)")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выбери действие…",
    )


def gender_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Мужчина"), KeyboardButton(text="Женщина")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def looking_for_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Ищу мужчин"), KeyboardButton(text="Ищу женщин")],
            [KeyboardButton(text="Ищу всех")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
