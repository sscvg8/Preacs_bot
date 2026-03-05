from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from tinder_bot.database.db import get_user_by_telegram_id, get_user_matches
from tinder_bot.utils.helpers import format_contact

router = Router()


async def _handle_matches(message: Message, session: AsyncSession) -> None:
    """Обработка просмотра мэтчей (используется для команды и кнопки)."""
    if not message.from_user:
        return

    me = await get_user_by_telegram_id(session, message.from_user.id)
    if not me:
        await message.answer("Сначала нужно зарегистрироваться: /start")
        return

    users = await get_user_matches(session, me.id)
    if not users:
        await message.answer("Пока нет мэтчей 😔\nЛистай анкеты: /browse")
        return

    await message.answer(f"🎉 Твои мэтчи: {len(users)}")
    for u in users:
        contact = format_contact(u.telegram_id, u.username)
        caption_lines = [
            f"{u.name}, {u.age}",
        ]
        if u.city:
            caption_lines.append(f"Город: {u.city}")
        if u.workplace:
            caption_lines.append(f"Учёба/работа: {u.workplace}")
        caption_lines.append(f"Кого ищет: {u.looking_for or 'Не указано'}")
        if u.useful_for:
            caption_lines.append(f"Чем может быть полезен: {u.useful_for}")
        caption_lines.extend(["", u.bio, "", f"Контакт: {contact}"])
        caption = "\n".join(caption_lines)
        if u.photo_id:
            await message.answer_photo(u.photo_id, caption=caption)
        else:
            await message.answer(caption)


@router.message(Command("matches"))
async def cmd_matches(message: Message, session: AsyncSession) -> None:
    await _handle_matches(message, session)


@router.message(F.text.contains("Мэтчи"))
async def btn_matches(message: Message, session: AsyncSession) -> None:
    await _handle_matches(message, session)

