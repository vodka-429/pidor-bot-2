# Fake sublime telegram bot sources

![Tests](https://github.com/vodka-429/pidor-bot-2/actions/workflows/tests.yml/badge.svg)

This is _FAKE_ sources just **_imitating_** the functionality similar to the one by SublimeBot in Telegram

## Prerequisites

* (Optionally) Install Python 3.11+ and/or Docker
* Create `.env` file and put `TELEGRAM_BOT_API_TOKEN=<token>` there
* The bot uses `python-telegram-bot` v21.7 (async/await based)

## Installation

* Clone repository `git clone git@github.com:vodka-429/pidor-bot-2/`
* Create virtual environment `python -m venv venv`
* Activate venv `source venv/bin/activate`
* Install all dependencies `pip3 install -r requirements.txt`

## Usage

Bot reads Telegram Bot Token from both `.env` file in current folder and also
`TELEGDAM_BOT_API_TOKEN` environmental variable

* Activate venv `source venv/bin/activate`
* Setup telegram bot token `export TELEGDAM_BOT_API_TOKEN=<token>`
* Start the bot `python3 main.py`

## Docker

* Build the image `docker build . -t <imagename>`
* Run docker image directly `docker run --rm --env-file=.env -it <imagename>`
* or by `docker-compose up` and `.env` file with token

## Новые функции

### Драматические сообщения о пропущенных днях

Когда вы вызываете команду `/pidor`, бот теперь проверяет, сколько дней прошло с последнего розыгрыша. Если были пропущенные дни, бот отправит драматическое сообщение перед обычным розыгрышем. Уровень драматизма зависит от количества пропущенных дней:

* 1 день - легкое напоминание
* 2-3 дня - более серьезное предупреждение
* 4-7 дней - драматическое сообщение
* 8-14 дней - очень драматическое сообщение
* 15-30 дней - критическое предупреждение
* 31+ дней - апокалиптическое сообщение

### Система финального голосования

В конце года (29-30 декабря) доступна специальная система для распределения пропущенных дней:

**Команды:**
* `/pidormissed` - показывает список всех пропущенных дней в текущем году
* `/pidorfinal` - запускает финальное голосование (доступно только 29-30 декабря)
* `/pidorfinalstatus` - показывает текущий статус голосования

**Как работает взвешенное голосование:**
1. Голосование можно запустить только если пропущено менее 10 дней
2. Каждый игрок может проголосовать за любого участника
3. Вес голоса каждого игрока равен количеству его побед в текущем году
4. Победитель получает все пропущенные дни в свою статистику

**Пример:**
Если Игрок А выиграл 50 раз в году и проголосовал за Игрока Б, это считается как 50 голосов. Если Игрок В выиграл 30 раз и тоже проголосовал за Игрока Б, то Игрок Б получит 80 взвешенных голосов.


## Миграция на python-telegram-bot v21.x

Проект был мигрирован с `python-telegram-bot==13.15` на `python-telegram-bot==21.7` для улучшения стабильности и исправления проблем с обработкой callback queries (кнопки голосования).

### Основные изменения в v21.x

**Breaking Changes:**
* **Async/Await**: Все handlers теперь асинхронные. Используйте `async def` и `await` для всех операций с ботом
* **Application вместо Updater**: Новый способ инициализации - `Application.builder().token(token).build()`
* **Filters с маленькой буквы**: `Filters.text` → `filters.TEXT`, `Filters.command` → `filters.COMMAND`
* **ParseMode как строка**: `ParseMode.MARKDOWN_V2` → `"MarkdownV2"`
* **Context types**: Используется `ContextTypes.DEFAULT_TYPE` вместо `CallbackContext`
* **Middleware**: Регистрация через `application.add_handler()` с параметром `block=False`

### Улучшения в v21.x

* **Надёжная обработка callback queries**: Улучшенная система обработки updates предотвращает проблемы с нереагирующими кнопками
* **Стабильный long polling**: Более надёжная работа с длительными соединениями
* **Лучшая обработка ошибок**: Улучшенная система обработки таймаутов и ошибок сети
* **Async/await**: Предотвращает блокировки и улучшает производительность

### Требования

* Python 3.11 или выше (рекомендуется 3.11+)
* `python-telegram-bot==21.7`
* `pytest-asyncio` для запуска тестов

### Troubleshooting

**Проблема: "RuntimeError: This event loop is already running"**
* Решение: Убедитесь, что используете `asyncio.run()` только один раз в точке входа приложения

**Проблема: "TypeError: object NoneType can't be used in 'await' expression"**
* Решение: Проверьте, что все bot API методы вызываются с `await` (например, `await update.message.reply_text()`)

**Проблема: Кнопки не реагируют на нажатия**
* Решение: Убедитесь, что `CallbackQueryHandler` зарегистрирован и callback_data корректно установлен при создании кнопок

**Проблема: Тесты падают с ошибками async**
* Решение: Добавьте декоратор `@pytest.mark.asyncio` к async тестам и используйте `AsyncMock` вместо `MagicMock`

**Проблема: "AttributeError: module 'telegram' has no attribute 'ParseMode'"**
* Решение: Замените `ParseMode.MARKDOWN_V2` на строку `"MarkdownV2"`

**Проблема: "ImportError: cannot import name 'Filters'"**
* Решение: Замените `from telegram.ext import Filters` на `from telegram.ext import filters` (lowercase)

### Откат на предыдущую версию

Если необходимо откатиться на v13.15:
```bash
git revert HEAD
pip install python-telegram-bot==13.15
```

Обратите внимание: v13.15 может иметь проблемы с обработкой callback queries в некоторых сценариях.
