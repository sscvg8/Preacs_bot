## Tinder bot (Studfest 2026) — MVP

### Что это
Telegram-бот для знакомств (аналог Tinder): регистрация, просмотр анкет, лайки/дизлайки, мэтчи и выдача контакта при взаимном лайке.

### Стек
- Python 3.10+
- aiogram 3.x
- SQLAlchemy 2.x (async)
- SQLite

### Установка
1) Создай и активируй виртуальное окружение

2) Установи зависимости:

```bash
pip install -r requirements.txt
```

3) Создай файл `.env` в корне проекта:

```env
BOT_TOKEN=123456:ABCDEF...
DB_URL=sqlite+aiosqlite:///./tinder.db
REQUIRED_CHANNEL_1=@my_channel_1
REQUIRED_CHANNEL_2=@my_channel_2
REQUIRED_CHANNEL_3=@my_channel_3
REQUIRED_CHANNEL_4=@my_channel_4
```

### Важно про Python на Windows
Рекомендуемый Python: **3.11/3.12**. На Python 3.13 некоторые зависимости (например `pydantic-core`) могут требовать сборку через Rust.

### Запуск

```bash
python -m tinder_bot.bot
```

### Команды
- `/start` — регистрация
- `/browse` — просмотр анкет
- `/matches` — мои мэтчи
- `/profile` — моя анкета
