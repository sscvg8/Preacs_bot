from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from tinder_bot.database.db import get_user_by_telegram_id, update_user_fields
from tinder_bot.keyboards.reply import gender_kb, main_menu_kb

router = Router()


class EditProfileFSM(StatesGroup):
    name = State()
    age = State()
    gender = State()
    photo = State()
    city = State()
    workplace = State()
    looking_for = State()
    useful_for = State()
    bio = State()


def _profile_kb(is_active: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить анкету", callback_data="profile:edit_menu")],
        ]
    )


def _edit_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Имя", callback_data="profile:edit:name")],
            [InlineKeyboardButton(text="Возраст", callback_data="profile:edit:age")],
            [InlineKeyboardButton(text="Пол", callback_data="profile:edit:gender")],
            [InlineKeyboardButton(text="Фото", callback_data="profile:edit:photo")],
            [InlineKeyboardButton(text="Город", callback_data="profile:edit:city")],
            [InlineKeyboardButton(text="Учёба/работа", callback_data="profile:edit:workplace")],
            [InlineKeyboardButton(text="Кого ищу", callback_data="profile:edit:looking_for")],
            [InlineKeyboardButton(text="Чем полезен", callback_data="profile:edit:useful_for")],
            [InlineKeyboardButton(text="Bio", callback_data="profile:edit:bio")],
            [InlineKeyboardButton(text="Отмена", callback_data="profile:edit:cancel")],
        ]
    )


def _normalize_gender(text: str) -> str | None:
    t = text.strip().lower()
    if t in {"м", "муж", "мужчина", "male"}:
        return "male"
    if t in {"ж", "жен", "женщина", "female"}:
        return "female"
    return None


def _resolve_telegram_user_id(message: Message) -> int | None:
    """
    В личных чатах message.chat.id == telegram_id пользователя.
    Для сообщений, отправленных ботом, message.from_user указывает на бота,
    поэтому используем chat.id как fallback.
    """
    if message.from_user and not getattr(message.from_user, "is_bot", False):
        return message.from_user.id
    if message.chat:
        return message.chat.id
    return None


async def _handle_profile(message: Message, session: AsyncSession) -> None:
    """Обработка просмотра профиля (используется для команды и кнопки)."""
    tg_id = _resolve_telegram_user_id(message)
    if not tg_id:
        return

    me = await get_user_by_telegram_id(session, tg_id)
    if not me:
        await message.answer("Сначала нужно зарегистрироваться: /start")
        return

    gender_h = "Мужчина" if me.gender == "male" else "Женщина"
    status_h = "активна ✅" if me.is_active else "неактивна ⛔️"
    looking_h = me.looking_for or "Не указано"

    caption_lines = [
        f"📌 Твоя анкета ({status_h})",
        "",
        f"{me.name}, {me.age}",
        f"Пол: {gender_h}",
    ]
    if me.city:
        caption_lines.append(f"Город: {me.city}")
    if me.workplace:
        caption_lines.append(f"Учёба/работа: {me.workplace}")
    caption_lines.append(f"Кого ищешь: {looking_h}")
    if me.useful_for:
        caption_lines.append(f"Чем могу быть полезен: {me.useful_for}")
    caption_lines.extend(["", me.bio])
    caption = "\n".join(caption_lines)
    if me.photo_id:
        await message.answer_photo(me.photo_id, caption=caption, reply_markup=_profile_kb(me.is_active))
    else:
        await message.answer(caption, reply_markup=_profile_kb(me.is_active))


@router.message(Command("profile"))
async def cmd_profile(message: Message, session: AsyncSession) -> None:
    await _handle_profile(message, session)


@router.message(F.text.contains("Моя анкета"))
async def btn_profile(message: Message, session: AsyncSession) -> None:
    await _handle_profile(message, session)


@router.callback_query(F.data == "profile:edit_menu")
async def cb_profile_edit_menu(call: CallbackQuery, session: AsyncSession) -> None:
    if not call.from_user or not call.message:
        return

    me = await get_user_by_telegram_id(session, call.from_user.id)
    if not me:
        await call.answer("Сначала /start")
        return

    await call.answer()
    await call.message.answer("Что хочешь изменить?", reply_markup=_edit_menu_kb())


async def _start_edit(field: str, message: Message, state: FSMContext) -> None:
    await state.clear()
    if field == "name":
        await state.set_state(EditProfileFSM.name)
        await message.answer(
            "Введи новое имя. Для отмены — /cancel",
            reply_markup=ReplyKeyboardRemove(),
        )
    elif field == "age":
        await state.set_state(EditProfileFSM.age)
        await message.answer(
            "Укажи новый возраст. Для отмены — /cancel",
            reply_markup=ReplyKeyboardRemove(),
        )
    elif field == "gender":
        await state.set_state(EditProfileFSM.gender)
        await message.answer(
            "Выбери пол:", reply_markup=gender_kb()
        )
    elif field == "photo":
        await state.set_state(EditProfileFSM.photo)
        await message.answer("Пришли новое фото для анкеты. Для отмены — /cancel")
    elif field == "city":
        await state.set_state(EditProfileFSM.city)
        await message.answer(
            "Введи город проживания. Для отмены — /cancel",
            reply_markup=ReplyKeyboardRemove(),
        )
    elif field == "workplace":
        await state.set_state(EditProfileFSM.workplace)
        await message.answer(
            "Где ты учишься или работаешь?. Для отмены — /cancel",
            reply_markup=ReplyKeyboardRemove(),
        )
    elif field == "looking_for":
        await state.set_state(EditProfileFSM.looking_for)
        await message.answer(
            "Кого ты ищешь? Напиши специальность/роль. Для отмены — /cancel",
            reply_markup=ReplyKeyboardRemove(),
        )
    elif field == "useful_for":
        await state.set_state(EditProfileFSM.useful_for)
        await message.answer(
            "Чем ты можешь быть полезен?. Для отмены — /cancel",
            reply_markup=ReplyKeyboardRemove(),
        )
    elif field == "bio":
        await state.set_state(EditProfileFSM.bio)
        await message.answer(
            "Напиши новое описание (10–700 символов). Для отмены — /cancel",
            reply_markup=ReplyKeyboardRemove(),
        )


@router.callback_query(F.data.startswith("profile:edit:"))
async def cb_profile_edit_field(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if not call.from_user or not call.message:
        return

    me = await get_user_by_telegram_id(session, call.from_user.id)
    if not me:
        await call.answer("Сначала /start")
        return

    _, _, field = call.data.partition("profile:edit:")
    if field == "cancel":
        await state.clear()
        await call.answer("Отменено")
        # Удаляем сообщение с меню редактирования
        try:
            await call.message.delete()
        except Exception:
            pass
        # Покажем профиль в этом же чате
        await _handle_profile(call.message, session)
        return

    if field not in {"name", "age", "gender", "photo", "city", "workplace", "looking_for", "useful_for", "bio"}:
        await call.answer("Неизвестное поле")
        return

    await call.answer()
    await _start_edit(field, call.message, state)


async def _ensure_user(message: Message, session: AsyncSession):
    tg_id = _resolve_telegram_user_id(message)
    if not tg_id:
        return None
    return await get_user_by_telegram_id(session, tg_id)


async def _apply_update_and_show(message: Message, session: AsyncSession, state: FSMContext, **fields: object) -> None:
    me = await _ensure_user(message, session)
    if not me:
        await message.answer("Сначала нужно зарегистрироваться: /start")
        await state.clear()
        return

    await update_user_fields(session, me.id, **fields)
    await state.clear()
    await message.answer("Изменения сохранены ✅")
    await _handle_profile(message, session)


def _is_cancel(text: str | None) -> bool:
    if not text:
        return False
    return text.strip().lower() in {"/cancel", "отмена"}


def _has_forbidden_at(value: str) -> bool:
    """Запрещаем символ @, чтобы пользователи не оставляли соцсети/ники."""
    return "@" in value


@router.message(EditProfileFSM.name, F.text)
async def edit_name(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if _is_cancel(message.text):
        await state.clear()
        await message.answer("Изменение отменено.")
        await _handle_profile(message, session)
        return

    name = (message.text or "").strip()
    if _has_forbidden_at(name):
        await message.answer("Нельзя использовать символ @. Напиши без соцсетей/ников.")
        return
    if len(name) < 2 or len(name) > 64:
        await message.answer("Имя должно быть от 2 до 64 символов. Попробуй ещё раз.")
        return

    await _apply_update_and_show(message, session, state, name=name)


@router.message(EditProfileFSM.age, F.text)
async def edit_age(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if _is_cancel(message.text):
        await state.clear()
        await message.answer("Изменение отменено.")
        await _handle_profile(message, session)
        return

    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Возраст нужно указать числом. Например: 21")
        return
    age = int(text)
    if age < 18 or age > 100:
        await message.answer("Возраст должен быть от 18 до 100. Попробуй ещё раз.")
        return

    await _apply_update_and_show(message, session, state, age=age)


@router.message(EditProfileFSM.gender, F.text)
async def edit_gender(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if _is_cancel(message.text):
        await state.clear()
        await message.answer("Изменение отменено.")
        await _handle_profile(message, session)
        return

    gender = _normalize_gender(message.text or "")
    if not gender:
        await message.answer("Выбери вариант кнопкой: Мужчина / Женщина", reply_markup=gender_kb())
        return

    await _apply_update_and_show(message, session, state, gender=gender)


@router.message(EditProfileFSM.photo, F.photo)
async def edit_photo(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if _is_cancel(message.caption):
        await state.clear()
        await message.answer("Изменение отменено")
        await _handle_profile(message, session)
        return

    if not message.photo:
        await message.answer("Нужно прислать фото (изображение)")
        return
    photo = message.photo[-1]
    await _apply_update_and_show(message, session, state, photo_id=photo.file_id)


@router.message(EditProfileFSM.photo)
async def edit_photo_invalid(message: Message) -> None:
    await message.answer("Пришли фото (изображение). Для отмены используй /cancel")


@router.message(EditProfileFSM.city, F.text)
async def edit_city(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if _is_cancel(message.text):
        await state.clear()
        await message.answer("Изменение отменено")
        await _handle_profile(message, session)
        return

    city = (message.text or "").strip()
    if _has_forbidden_at(city):
        await message.answer("Нельзя использовать символ @. Напиши без соцсетей/ников.")
        return
    if len(city) < 2 or len(city) > 80:
        await message.answer("Город должен быть от 2 до 80 символов. Попробуй ещё раз")
        return

    await _apply_update_and_show(message, session, state, city=city)


@router.message(EditProfileFSM.workplace, F.text)
async def edit_workplace(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if _is_cancel(message.text):
        await state.clear()
        await message.answer("Изменение отменено")
        await _handle_profile(message, session)
        return

    workplace = (message.text or "").strip()
    if _has_forbidden_at(workplace):
        await message.answer("Нельзя использовать символ @. Напиши без соцсетей/ников.")
        return
    if len(workplace) < 2 or len(workplace) > 120:
        await message.answer("Учёба/работа должна быть от 2 до 120 символов. Попробуй ещё раз")
        return

    await _apply_update_and_show(message, session, state, workplace=workplace)


@router.message(EditProfileFSM.looking_for, F.text)
async def edit_looking_for(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if _is_cancel(message.text):
        await state.clear()
        await message.answer("Изменение отменено")
        await _handle_profile(message, session)
        return

    lf = (message.text or "").strip()
    if _has_forbidden_at(lf):
        await message.answer("Нельзя использовать символ @. Напиши без соцсетей/ников.")
        return
    if len(lf) < 2 or len(lf) > 120:
        await message.answer("Опиши, кого ищешь (2–120 символов)")
        return

    await _apply_update_and_show(message, session, state, looking_for=lf)


@router.message(EditProfileFSM.useful_for, F.text)
async def edit_useful_for(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if _is_cancel(message.text):
        await state.clear()
        await message.answer("Изменение отменено")
        await _handle_profile(message, session)
        return

    useful_for = (message.text or "").strip()
    if _has_forbidden_at(useful_for):
        await message.answer("Нельзя использовать символ @. Напиши без соцсетей/ников.")
        return
    if len(useful_for) < 5 or len(useful_for) > 300:
        await message.answer("Опиши, чем можешь быть полезен (5–300 символов)")
        return

    await _apply_update_and_show(message, session, state, useful_for=useful_for)


@router.message(EditProfileFSM.bio, F.text)
async def edit_bio(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if _is_cancel(message.text):
        await state.clear()
        await message.answer("Изменение отменено")
        await _handle_profile(message, session)
        return

    bio = (message.text or "").strip()
    if _has_forbidden_at(bio):
        await message.answer("Нельзя использовать символ @. Напиши без соцсетей/ников.")
        return
    if len(bio) < 10:
        await message.answer("Сделай описание чуть подробнее (минимум 10 символов)")
        return
    if len(bio) > 700:
        await message.answer("Слишком длинно — максимум 700 символов")
        return

    await _apply_update_and_show(message, session, state, bio=bio)

