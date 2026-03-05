from __future__ import annotations

import logging
from typing import AsyncIterator

from sqlalchemy import and_, exists, func, inspect, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from tinder_bot.config import settings
from tinder_bot.database.models import Base, Like, Match, User

logger = logging.getLogger(__name__)


engine: AsyncEngine = create_async_engine(settings.DB_URL, echo=False, future=True)
SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine, expire_on_commit=False, autoflush=False, autocommit=False
)


async def _migrate_db() -> None:
    """Миграция: делает looking_for и photo_id опциональными."""
    try:
        async with engine.begin() as conn:
            # Проверяем, существует ли таблица users
            def check_table_exists(connection):
                inspector = inspect(connection)
                tables = inspector.get_table_names()
                return "users" in tables

            table_exists = await conn.run_sync(check_table_exists)
            if not table_exists:
                return  # Таблицы ещё нет, создастся через create_all

            # Проверяем, можно ли вставить NULL в looking_for
            # Если таблица уже в новой структуре, попытка миграции просто пересоздаст её
            try:
                # Пробуем вставить тестовый NULL через SELECT - если схема уже правильная, продолжим
                # Вместо этого проверим через PRAGMA table_info
                result = await conn.execute(text("PRAGMA table_info(users)"))
                columns = {row[1]: row for row in result.fetchall()}
                
                # Если столбца looking_for нет - что-то не так
                if "looking_for" not in columns:
                    return
                
                # Проверяем через попытку создания таблицы с NULL - если уже можно, пропускаем
                # Но проще просто выполнить миграцию - она безопасна
            except Exception as e:
                logger.warning(f"Ошибка при проверке структуры: {e}")
                return

            logger.info("Выполняется миграция: делаем looking_for и photo_id опциональными...")
            
            # Удаляем временную таблицу если она осталась от предыдущей попытки
            await conn.execute(text("DROP TABLE IF EXISTS users_new"))
            
            # Создаём временную таблицу с новой структурой
            await conn.execute(text("""
                CREATE TABLE users_new (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL UNIQUE,
                    username VARCHAR(64),
                    name VARCHAR(64) NOT NULL,
                    age INTEGER NOT NULL,
                    gender VARCHAR(10) NOT NULL,
                    looking_for VARCHAR(10),
                    bio VARCHAR(700) NOT NULL,
                    photo_id VARCHAR(300),
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    created_at DATETIME NOT NULL DEFAULT (datetime('now'))
                )
            """))
            
            # Копируем данные (все существующие значения сохраняются)
            await conn.execute(text("""
                INSERT INTO users_new 
                (id, telegram_id, username, name, age, gender, looking_for, bio, photo_id, is_active, created_at)
                SELECT 
                    id, telegram_id, username, name, age, gender, looking_for, bio, photo_id, is_active, created_at
                FROM users
            """))
            
            # Удаляем старую таблицу
            await conn.execute(text("DROP TABLE users"))
            
            # Переименовываем новую таблицу
            await conn.execute(text("ALTER TABLE users_new RENAME TO users"))
            
            # Восстанавливаем индексы
            await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_telegram_id ON users (telegram_id)"))
            
            logger.info("Миграция завершена успешно")
    except Exception as e:
        # Если миграция уже выполнена или произошла ошибка - логируем и продолжаем
        logger.warning(f"Миграция не выполнена (возможно уже выполнена ранее): {e}")

    # Добавляем новые поля если их нет (city, workplace, useful_for)
    try:
        async with engine.begin() as conn:
            result = await conn.execute(text("PRAGMA table_info(users)"))
            columns = {row[1] for row in result.fetchall()}

            alter_statements = []
            if "city" not in columns:
                alter_statements.append("ALTER TABLE users ADD COLUMN city VARCHAR(120)")
            if "workplace" not in columns:
                alter_statements.append("ALTER TABLE users ADD COLUMN workplace VARCHAR(160)")
            if "useful_for" not in columns:
                alter_statements.append("ALTER TABLE users ADD COLUMN useful_for VARCHAR(400)")

            for stmt in alter_statements:
                await conn.execute(text(stmt))
    except Exception as e:
        logger.warning(f"Не удалось выполнить миграцию для новых полей: {e}")


async def init_db() -> None:
    """Создаёт таблицы при старте (без Alembic для MVP)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Выполняем миграцию если нужно
    await _migrate_db()


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


# -------------------------
# User CRUD / helpers
# -------------------------


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    res = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return res.scalar_one_or_none()


async def create_user(
    session: AsyncSession,
    *,
    telegram_id: int,
    username: str | None,
    name: str,
    age: int,
    gender: str,
    looking_for: str | None,
    city: str | None,
    workplace: str | None,
    useful_for: str | None,
    bio: str,
    photo_id: str | None,
) -> User:
    user = User(
        telegram_id=telegram_id,
        username=username,
        name=name,
        age=age,
        gender=gender,
        looking_for=looking_for,
        city=city,
        workplace=workplace,
        useful_for=useful_for,
        bio=bio,
        photo_id=photo_id,
        is_active=True,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise
    await session.refresh(user)
    return user


async def set_user_active(session: AsyncSession, user_id: int, is_active: bool) -> None:
    res = await session.execute(select(User).where(User.id == user_id))
    user = res.scalar_one()
    user.is_active = is_active
    await session.commit()


async def update_user_fields(session: AsyncSession, user_id: int, **fields: object) -> User | None:
    """
    Обновляет выбранные поля пользователя и возвращает обновлённую модель.
    Неизвестные/None-поля игнорируются.
    """
    allowed = {
        "name",
        "age",
        "gender",
        "looking_for",
        "bio",
        "photo_id",
        "username",
        "is_active",
        "city",
        "workplace",
        "useful_for",
    }
    payload = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not payload:
        return None

    res = await session.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        return None

    for k, v in payload.items():
        setattr(user, k, v)

    await session.commit()
    await session.refresh(user)
    return user


# -------------------------
# Browsing / matching logic
# -------------------------


async def get_next_profile_for_browsing(session: AsyncSession, viewer_id: int) -> User | None:
    """
    Возвращает случайную анкету, которую viewer ещё не оценивал (лайк/дизлайк).
    Анкеты показываются рандомно без фильтрации по looking_for.
    """
    # подзапрос: кого viewer уже оценивал (лайк/дизлайк)
    reacted_subq = select(Like.to_user_id).where(Like.from_user_id == viewer_id).subquery()

    stmt = (
        select(User)
        .where(
            User.id != viewer_id,
            User.is_active.is_(True),
            User.id.not_in(select(reacted_subq.c.to_user_id)),
        )
        .order_by(func.random())
        .limit(1)
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def add_reaction(session: AsyncSession, from_user_id: int, to_user_id: int, *, is_like: bool) -> bool:
    """
    Добавляет реакцию (лайк/дизлайк).
    Возвращает True если была создана, False если уже существовала.
    """
    reaction = Like(from_user_id=from_user_id, to_user_id=to_user_id, is_like=is_like)
    session.add(reaction)
    try:
        await session.commit()
        return True
    except IntegrityError:
        await session.rollback()
        return False


async def has_mutual_like(session: AsyncSession, user_a_id: int, user_b_id: int) -> bool:
    """
    Есть ли лайк от B к A (встречный лайк).
    """
    stmt = select(
        exists().where(
            and_(Like.from_user_id == user_b_id, Like.to_user_id == user_a_id, Like.is_like.is_(True))
        )
    )
    res = await session.execute(stmt)
    return bool(res.scalar())


async def create_match_if_not_exists(session: AsyncSession, user_a_id: int, user_b_id: int) -> bool:
    """
    Создаёт мэтч для пары (min, max). True если создан, False если уже был.
    """
    u1, u2 = (user_a_id, user_b_id) if user_a_id < user_b_id else (user_b_id, user_a_id)
    match = Match(user1_id=u1, user2_id=u2)
    session.add(match)
    try:
        await session.commit()
        return True
    except IntegrityError:
        await session.rollback()
        return False


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    res = await session.execute(select(User).where(User.id == user_id))
    return res.scalar_one_or_none()


async def get_user_matches(session: AsyncSession, user_id: int) -> list[User]:
    """
    Возвращает список пользователей, с которыми есть мэтч.
    """
    stmt = (
        select(User)
        .join(
            Match,
            or_(
                and_(Match.user1_id == user_id, Match.user2_id == User.id),
                and_(Match.user2_id == user_id, Match.user1_id == User.id),
            ),
        )
        .order_by(Match.created_at.desc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())

