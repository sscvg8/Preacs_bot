from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from tinder_bot.config import settings
from tinder_bot.database.db import SessionLocal, init_db
from tinder_bot.handlers import browsing, matches, profile, registration


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


async def set_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Регистрация / старт"),
            BotCommand(command="browse", description="Смотреть анкеты"),
            BotCommand(command="matches", description="Мои мэтчи"),
            BotCommand(command="profile", description="Моя анкета"),
        ]
    )


class DbSessionMiddleware(BaseMiddleware):
    """
    Прокидываем AsyncSession в data['session'] для каждого апдейта.
    """

    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        async with SessionLocal() as session:
            data["session"] = session
            return await handler(event, data)


class DeleteCallbackMessageMiddleware(BaseMiddleware):
    """
    UX: при нажатии любой inline-кнопки (CallbackQuery) удаляем сообщение бота с этой кнопкой.
    Это делает интерфейс "чистым": вместо редактирования старых сообщений бот присылает новые.
    """

    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        if isinstance(event, CallbackQuery) and event.message:
            # Не удаляем сообщения с проверкой подписки, просмотром анкет и согласием на ОПД
            # (там нужна сохранность кнопок-ссылок, анкет и согласия)
            if event.data and event.data not in {"subcheck"} and not event.data.startswith(("like:", "dislike:", "consent:")):
                try:
                    await event.message.delete()
                except Exception:
                    # Нет прав/сообщение уже удалено/слишком старое — не критично
                    pass
        return await handler(event, data)


async def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)

    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    dp.update.middleware(DbSessionMiddleware())
    # Важно: для CallbackQuery middleware вешаем на соответствующий "observer",
    # иначе на dp.update сюда приходит Update, а не CallbackQuery.
    dp.callback_query.middleware(DeleteCallbackMessageMiddleware())

    dp.include_router(registration.router)
    dp.include_router(profile.router)
    dp.include_router(browsing.router)
    dp.include_router(matches.router)

    await init_db()
    await set_commands(bot)

    logger.info("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

