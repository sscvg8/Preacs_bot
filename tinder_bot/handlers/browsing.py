from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from tinder_bot.database.db import (
    add_reaction,
    create_match_if_not_exists,
    get_next_profile_for_browsing,
    get_user_by_id,
    get_user_by_telegram_id,
    has_mutual_like,
)
from tinder_bot.keyboards.inline import browse_kb
from tinder_bot.utils.helpers import format_contact

logger = logging.getLogger(__name__)

router = Router()


async def _send_profile(message: Message, viewer_id: int, session: AsyncSession) -> None:
    candidate = await get_next_profile_for_browsing(session, viewer_id)
    if not candidate:
        await message.answer("Пока нет подходящих анкет 😔\nПопробуй позже.")
        return
    caption_lines = [
        f"{candidate.name}, {candidate.age}",
    ]
    if candidate.city:
        caption_lines.append(f"Город: {candidate.city}")
    if candidate.workplace:
        caption_lines.append(f"Учёба/работа: {candidate.workplace}")
    caption_lines.append(f"Кого ищет: {candidate.looking_for or 'Не указано'}")
    if candidate.useful_for:
        caption_lines.append(f"Чем может быть полезен: {candidate.useful_for}")
    caption_lines.extend(["", candidate.bio])
    caption = "\n".join(caption_lines)
    if candidate.photo_id:
        await message.answer_photo(candidate.photo_id, caption=caption, reply_markup=browse_kb(candidate.id))
    else:
        await message.answer(caption, reply_markup=browse_kb(candidate.id))


async def _handle_browse(message: Message, session: AsyncSession) -> None:
    """Обработка просмотра анкет (используется для команды и кнопки)."""
    if not message.from_user:
        return

    me = await get_user_by_telegram_id(session, message.from_user.id)
    if not me:
        await message.answer("Сначала нужно зарегистрироваться: /start")
        return
    if not me.is_active:
        await message.answer("Твоя анкета деактивирована. Активируй её через /profile.")
        return

    await _send_profile(message, me.id, session)


@router.message(Command("browse"))
async def cmd_browse(message: Message, session: AsyncSession) -> None:
    await _handle_browse(message, session)


@router.message(F.text.contains("Смотреть анкеты"))
async def btn_browse(message: Message, session: AsyncSession) -> None:
    await _handle_browse(message, session)


@router.callback_query(F.data.startswith("like:"))
async def cb_like(call: CallbackQuery, session: AsyncSession) -> None:
    if not call.from_user or not call.message:
        return

    me = await get_user_by_telegram_id(session, call.from_user.id)
    if not me:
        await call.answer("Сначала /start")
        return

    try:
        target_id = int(call.data.split(":", 1)[1])
    except Exception:
        await call.answer("Ошибка данных")
        return

    if target_id == me.id:
        await call.answer("Это ты 🙂")
        return

    await add_reaction(session, me.id, target_id, is_like=True)
    await call.answer("❤️")

    # Проверяем взаимный лайк
    if await has_mutual_like(session, me.id, target_id):
        created = await create_match_if_not_exists(session, me.id, target_id)
        # Уведомляем обоих пользователей при взаимном лайке
        target = await get_user_by_id(session, target_id)
        if target:
            me_contact = format_contact(me.telegram_id, me.username)
            target_contact = format_contact(target.telegram_id, target.username)
            try:
                # Уведомляем того, кто только что лайкнул
                await call.bot.send_message(
                    me.telegram_id,
                    f"🎉 У вас мэтч с {target.name}!\nКонтакт: {target_contact}",
                )
                # Уведомляем второго пользователя (всегда при взаимном лайке)
                await call.bot.send_message(
                    target.telegram_id,
                    f"🎉 У вас мэтч с {me.name}!\nКонтакт: {me_contact}",
                )
            except Exception:
                logger.exception("Failed to notify match users")

    # Показать следующую анкету (в том же чате)
    await _send_profile(call.message, me.id, session)


@router.callback_query(F.data.startswith("dislike:"))
async def cb_dislike(call: CallbackQuery, session: AsyncSession) -> None:
    if not call.from_user or not call.message:
        return

    me = await get_user_by_telegram_id(session, call.from_user.id)
    if not me:
        await call.answer("Сначала /start")
        return

    try:
        target_id = int(call.data.split(":", 1)[1])
    except Exception:
        await call.answer("Ошибка данных")
        return

    if target_id == me.id:
        await call.answer("Это ты 🙂")
        return

    await add_reaction(session, me.id, target_id, is_like=False)
    await call.answer("👎")

    await _send_profile(call.message, me.id, session)

