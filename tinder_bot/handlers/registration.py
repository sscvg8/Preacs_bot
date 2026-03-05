from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from aiogram.enums import ChatMemberStatus
from sqlalchemy.ext.asyncio import AsyncSession

from tinder_bot.config import settings
from tinder_bot.database.db import create_user, get_user_by_telegram_id
from tinder_bot.keyboards.inline import required_subscription_kb, consent_kb
from tinder_bot.keyboards.reply import gender_kb, main_menu_kb

logger = logging.getLogger(__name__)

router = Router()


class RegistrationFSM(StatesGroup):
    consent = State()
    name = State()
    age = State()
    gender = State()
    photo = State()
    city = State()
    workplace = State()
    looking_for = State()
    useful_for = State()
    bio = State()


def _normalize_gender(text: str) -> str | None:
    t = text.strip().lower()
    if t in {"м", "муж", "мужчина", "male"}:
        return "male"
    if t in {"ж", "жен", "женщина", "female"}:
        return "female"
    return None


def _validate_text_field(value: str, *, min_len: int, max_len: int) -> bool:
    return min_len <= len(value) <= max_len


def _has_forbidden_at(value: str) -> bool:
    """Запрещаем символ @, чтобы пользователи не оставляли соцсети/ники."""
    return "@" in value


def _normalize_channel_ref(value: str) -> str | int:
    """
    Приводим ссылку на канал к формату, который понимает Telegram API:
    - '@username' для публичных каналов
    - int для ID (например -100123...)
    """
    v = (value or "").strip()
    if not v:
        return v
    # ID канала (или чат/супергруппа)
    if v.lstrip("-").isdigit():
        try:
            return int(v)
        except Exception:
            return v
    if not v.startswith("@"):
        v = f"@{v}"
    return v


async def _is_subscribed_to_all(bot, user_id: int) -> tuple[bool, list[str]]:
    """
    Проверяем подписку пользователя на все обязательные каналы.
    Возвращаем (ok, missing_channels_raw).
    """
    required = settings.required_channels
    if not required:
        return True, []

    # Валидные статусы подписчика
    valid_statuses = {
        ChatMemberStatus.CREATOR,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.RESTRICTED,  # Ограниченный, но подписан
    }

    missing: list[str] = []
    for raw in required:
        chat_id = _normalize_channel_ref(raw)
        try:
            member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        except Exception as e:
            # Если бот не админ/не в канале/канал приватный — Telegram не даст проверить.
            # В этом случае безопаснее считать, что подписки нет.
            logger.warning("Failed to check subscription for channel=%r: %s", raw, e)
            missing.append(raw)
            continue

        # Явно проверяем, что пользователь подписан (не LEFT и не KICKED)
        if member.status not in valid_statuses:
            logger.info("User %d not subscribed to channel %r (status: %s)", user_id, raw, member.status)
            missing.append(raw)

    return len(missing) == 0, missing


async def _start_flow(message: Message, state: FSMContext, session: AsyncSession) -> None:
    """
    Основная логика /start после успешной проверки подписки.
    """
    if not message.from_user:
        return

    tg_id = message.from_user.id
    existing = await get_user_by_telegram_id(session, tg_id)
    if existing:
        await state.clear()
        await message.answer(
            "Ты уже зарегистрирован ✅\n\n"
            "Используй /browse чтобы смотреть анкеты или /profile чтобы открыть свою",
            reply_markup=main_menu_kb(),
        )
        return

    # Показываем согласие на обработку персональных данных
    await state.clear()
    await state.set_state(RegistrationFSM.consent)
    
    consent_text = (
        "📋 <b>СОГЛАСИЕ НА ОБРАБОТКУ ПЕРСОНАЛЬНЫХ ДАННЫХ</b>\n\n"
        "<b>Оператор:</b> Центральный Преакселератор\n"
        "<b>Цель:</b> Организация нетворкинга участников открытия Преакселератора через Telegram-бот\n\n"
        "<b>Обрабатываемые данные:</b> имя, фотография, возраст, пол, город проживания, место учёбы/работы, информация о том, кого ищете и чем можете быть полезны, описание (bio).\n\n"
        "<b>Способы обработки:</b> автоматизированная и неавтоматизированная обработка (сбор, запись, систематизация, накопление, хранение, уточнение, извлечение, использование, удаление).\n\n"
        "<b>Цели обработки:</b>\n"
        "1. Создание профиля участника в системе нетворкинга\n"
        "2. Подбор контактов среди участников открытия Преакселератора\n"
        "3. Обеспечение взаимодействия между участниками мероприятия\n\n"
        "<b>Срок действия:</b> до 30 дней после завершения открытия Преакселератора или до отзыва согласия.\n\n"
        "<b>Ваши права:</b> получать информацию о наличии данных, требовать уточнения, блокирования или уничтожения данных, отозвать согласие в любой момент.\n\n"
        "<b>Передача третьим лицам:</b> персональные данные не передаются третьим лицам и не используются в рекламных или коммерческих целях.\n\n"
        "Согласие составлено в соответствии с Федеральным законом №152-ФЗ «О персональных данных».\n\n"
        "Для продолжения необходимо дать согласие:"
    )
    await message.answer(consent_text, reply_markup=consent_kb(), parse_mode="HTML")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, session: AsyncSession) -> None:
    """
    /start:
    - если пользователь уже зарегистрирован -> сообщаем и показываем меню
    - иначе запускаем FSM регистрации
    """
    if not message.from_user:
        return

    ok, _missing = await _is_subscribed_to_all(message.bot, message.from_user.id)
    if not ok:
        await state.clear()
        required = settings.required_channels
        labels: dict[str, str] = {}
        if len(required) > 0:
            labels[required[0]] = "Подписаться на Startup club"
        if len(required) > 1:
            labels[required[1]] = "Подписаться на Предпринимательский клуб"
        if len(required) > 2:
            labels[required[2]] = "Подписаться на организатора"
        if len(required) > 3:
            labels[required[3]] = "Подписаться на организатора"
        if len(required) > 4:
            labels[required[4]] = "Подписаться на организатора"
        if len(required) > 5:
            labels[required[5]] = "Подписаться на организатора"
        missing = _missing or required
        await message.answer(
            "Чтобы пользоваться ботом, подпишись на каналы и нажми «Проверить подписку»",
            reply_markup=required_subscription_kb(missing, labels=labels),
        )
        return

    await _start_flow(message, state, session)


@router.callback_query(F.data == "subcheck")
async def cb_subcheck(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if not call.from_user or not call.message:
        return

    ok, _missing = await _is_subscribed_to_all(call.bot, call.from_user.id)
    if not ok:
        required = settings.required_channels
        labels: dict[str, str] = {}
        if len(required) > 0:
            labels[required[0]] = "Подписаться на Startup club"
        if len(required) > 1:
            labels[required[1]] = "Подписаться на Предпринимательский клуб"
        if len(required) > 2:
            labels[required[2]] = "Подписаться на основателя клуба"
        missing = _missing or required
        # Показываем в чат (а не alert), какие именно каналы ещё нужны
        await call.message.answer(
            "Подписка ещё не найдена на всех каналах. Подпишись и нажми «Проверить подписку» ещё раз.",
            reply_markup=required_subscription_kb(missing, labels=labels),
        )
        await call.answer()
        return

    await call.answer("Подписка подтверждена ✅")
    await _start_flow(call.message, state, session)


@router.callback_query(F.data.startswith("consent:"))
async def cb_consent(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if not call.from_user or not call.message:
        return

    _, consent_value = call.data.split(":", 1)
    
    if consent_value == "yes":
        await call.answer("Согласие принято ✅")
        await state.set_state(RegistrationFSM.name)
        await call.message.answer(
            "Привет! Давай создадим анкету\n\nКак тебя зовут?",
            reply_markup=ReplyKeyboardRemove(),
        )
    elif consent_value == "no":
        await call.answer("Без согласия на обработку персональных данных регистрация невозможна", show_alert=True)
        await call.message.answer(
            "❌ Для использования бота необходимо дать согласие на обработку персональных данных.\n\n"
            "Если передумаешь, нажми /start и дай согласие."
        )


@router.message(RegistrationFSM.name, F.text)
async def reg_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if _has_forbidden_at(name):
        await message.answer("Нельзя использовать символ @. Напиши без соцсетей/ников.")
        return
    if len(name) < 2 or len(name) > 64:
        await message.answer("Имя должно быть от 2 до 64 символов. Попробуй ещё раз.")
        return

    await state.update_data(name=name)
    await state.set_state(RegistrationFSM.age)
    await message.answer("Сколько тебе лет?")


@router.message(RegistrationFSM.age, F.text)
async def reg_age(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Возраст нужно указать числом. Например: 21")
        return
    age = int(text)
    if age < 14 or age > 100:
        await message.answer("Возраст должен быть от 14 до 100. Попробуй ещё раз")
        return

    await state.update_data(age=age)
    await state.set_state(RegistrationFSM.gender)
    await message.answer("Укажи пол:", reply_markup=gender_kb())


@router.message(RegistrationFSM.gender, F.text)
async def reg_gender(message: Message, state: FSMContext) -> None:
    gender = _normalize_gender(message.text or "")
    if not gender:
        await message.answer("Выбери вариант кнопкой: Мужчина / Женщина", reply_markup=gender_kb())
        return

    await state.update_data(gender=gender)
    await state.set_state(RegistrationFSM.photo)
    await message.answer("Пришли фото для анкеты (одно изображение)", reply_markup=ReplyKeyboardRemove())


@router.message(RegistrationFSM.photo, F.photo)
async def reg_photo(message: Message, state: FSMContext) -> None:
    if not message.photo:
        await message.answer("Пришли именно фото (изображение)")
        return
    photo = message.photo[-1]
    await state.update_data(photo_id=photo.file_id)
    await state.set_state(RegistrationFSM.city)
    await message.answer("В каком городе живёшь?")


@router.message(RegistrationFSM.photo)
async def reg_photo_invalid(message: Message) -> None:
    await message.answer("Нужно прислать фото (изображение)")


@router.message(RegistrationFSM.city, F.text)
async def reg_city(message: Message, state: FSMContext) -> None:
    city = (message.text or "").strip()
    if _has_forbidden_at(city):
        await message.answer("Нельзя использовать символ @. Напиши без соцсетей/ников.")
        return
    if len(city) < 2 or len(city) > 80:
        await message.answer("Город должен быть от 2 до 80 символов. Попробуй ещё раз")
        return
    await state.update_data(city=city)
    await state.set_state(RegistrationFSM.workplace)
    await message.answer("Где учишься или работаешь?")


@router.message(RegistrationFSM.workplace, F.text)
async def reg_workplace(message: Message, state: FSMContext) -> None:
    workplace = (message.text or "").strip()
    if _has_forbidden_at(workplace):
        await message.answer("Нельзя использовать символ @. Напиши без соцсетей/ников.")
        return
    if len(workplace) < 2 or len(workplace) > 120:
        await message.answer("Укажи учебу/работу от 2 до 120 символов")
        return
    await state.update_data(workplace=workplace)
    await state.set_state(RegistrationFSM.looking_for)
    await message.answer("Кого ищешь? Напиши специальность/роль")


@router.message(RegistrationFSM.looking_for, F.text)
async def reg_looking_for(message: Message, state: FSMContext) -> None:
    lf_raw = (message.text or "").strip()
    if _has_forbidden_at(lf_raw):
        await message.answer("Нельзя использовать символ @. Напиши без соцсетей/ников.")
        return
    if not _validate_text_field(lf_raw, min_len=2, max_len=120):
        await message.answer("Укажи, кого ищешь. Например: дизайнеров, маркетологов, data scientists")
        return
    await state.update_data(looking_for=lf_raw)
    await state.set_state(RegistrationFSM.useful_for)
    await message.answer("Чем можешь быть полезен?", reply_markup=ReplyKeyboardRemove())


@router.message(RegistrationFSM.useful_for, F.text)
async def reg_useful_for(message: Message, state: FSMContext) -> None:
    useful_for = (message.text or "").strip()
    if _has_forbidden_at(useful_for):
        await message.answer("Нельзя использовать символ @. Напиши без соцсетей/ников.")
        return
    if len(useful_for) < 5 or len(useful_for) > 300:
        await message.answer("Опиши пользу от 5 до 300 символов")
        return
    await state.update_data(useful_for=useful_for)
    await state.set_state(RegistrationFSM.bio)
    await message.answer("Напиши короткое описание (bio), до 700 символов")


@router.message(RegistrationFSM.bio, F.text)
async def reg_bio(message: Message, state: FSMContext, session: AsyncSession) -> None:
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

    if not message.from_user:
        return

    data = await state.get_data()
    try:
        user = await create_user(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            name=data["name"],
            age=int(data["age"]),
            gender=data["gender"],
            looking_for=data.get("looking_for"),
            city=data.get("city"),
            workplace=data.get("workplace"),
            useful_for=data.get("useful_for"),
            bio=bio,
            photo_id=data.get("photo_id"),
        )
    except Exception:
        logger.exception("Failed to create user")
        await message.answer("Упс, не удалось сохранить анкету. Попробуй ещё раз позже")
        await state.clear()
        return

    await state.clear()

    gender_h = "Мужчина" if user.gender == "male" else "Женщина"
    caption_parts = [
        "✅ Анкета создана!",
        "",
        f"{user.name}, {user.age}",
        f"Пол: {gender_h}",
    ]
    if user.city:
        caption_parts.append(f"Город: {user.city}")
    if user.workplace:
        caption_parts.append(f"Учёба/работа: {user.workplace}")
    caption_parts.append(f"Кого ищу: {user.looking_for or 'Не указано'}")
    if user.useful_for:
        caption_parts.append(f"Чем могу быть полезен: {user.useful_for}")
    caption_parts.extend(["", user.bio])

    caption = "\n".join(caption_parts)
    if user.photo_id:
        await message.answer_photo(user.photo_id, caption=caption, reply_markup=main_menu_kb())
    else:
        await message.answer(caption, reply_markup=main_menu_kb())


@router.message(RegistrationFSM.bio)
async def reg_bio_invalid(message: Message) -> None:
    await message.answer("Bio нужно прислать текстом")

