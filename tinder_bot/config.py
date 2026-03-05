from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Настройки приложения.
    Берём значения из переменных окружения и/или .env.
    """

    # Ищем .env в корне проекта и (на всякий) внутри пакета tinder_bot/
    # Это удобно на Windows/IDE, когда рабочая директория может отличаться.
    model_config = SettingsConfigDict(
        env_file=(".env", "tinder_bot/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    BOT_TOKEN: str
    # Локальная SQLite в файле внутри папки проекта (по умолчанию ./tinder.db)
    DB_URL: str = "sqlite+aiosqlite:///./tinder.db"
    # Обязательная подписка (username каналов, можно с @). Если пусто — проверка отключена.
    REQUIRED_CHANNEL_1: str = ""
    REQUIRED_CHANNEL_2: str = ""
    REQUIRED_CHANNEL_3: str = ""
    REQUIRED_CHANNEL_4: str = ""
    REQUIRED_CHANNEL_5: str = ""
    REQUIRED_CHANNEL_6: str = ""

    @property
    def required_channels(self) -> list[str]:
        """Возвращает список обязательных каналов (из .env)."""
        channels: list[str] = []
        for raw in (
            self.REQUIRED_CHANNEL_1,
            self.REQUIRED_CHANNEL_2,
            self.REQUIRED_CHANNEL_3,
            self.REQUIRED_CHANNEL_4,
            self.REQUIRED_CHANNEL_5,
            self.REQUIRED_CHANNEL_6,
        ):
            v = (raw or "").strip()
            if not v:
                continue
            channels.append(v)
        return channels


settings = Settings()
