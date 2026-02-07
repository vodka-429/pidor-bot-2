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

## Configuration

The bot uses the following environment variables:

* `TELEGRAM_BOT_API_SECRET` - Telegram Bot API token (required)
* `GAME_CONFIG` - Path to JSON configuration file for game settings (optional, see below)
* `ALLOWED_FINAL_VOTING_CLOSERS` - Comma-separated list of usernames allowed to close final voting (optional, if not set all chat administrators can close voting)

### Game Configuration

Начиная с версии 2.0, бот использует централизованную систему конфигурации через JSON-файл. Это позволяет гибко настраивать параметры игры для каждого чата отдельно.

#### Переменная окружения GAME_CONFIG

Установите переменную окружения `GAME_CONFIG` с путем к JSON-файлу конфигурации:

```bash
export GAME_CONFIG=/path/to/game_config.json
```

#### Формат конфигурационного файла

```json
{
  "enabled_chats": [-1001392307997, -4608252738, -1002189152002, -1003671793100],
  "test_chat_id": -4608252738,
  "defaults": {
    "immunity_price": 10,
    "double_chance_price": 8,
    "prediction_price": 3,
    "reroll_price": 15,
    "coins_per_win": 4,
    "coins_per_command": 1,
    "prediction_reward": 30
  },
  "chat_overrides": {
    "-4608252738": {
      "immunity_price": 5,
      "max_missed_days_for_final_voting": 100,
      "reroll_enabled": true
    },
    "-1001392307997": {
      "reroll_enabled": false,
      "transfer_enabled": false
    }
  }
}
```

#### Параметры конфигурации

**Глобальные параметры:**
- `enabled_chats` - Список ID чатов, в которых бот активен (whitelist). Замена для `CHAT_WHITELIST`.
- `test_chat_id` - ID тестового чата для отладки. Замена для `TEST_CHAT_ID`.
- `defaults` - Значения по умолчанию для всех чатов.
- `chat_overrides` - Переопределения параметров для конкретных чатов.

**Цены в магазине (в пидоркоинах):**
- `immunity_price` - Цена защиты от выбора пидором (по умолчанию: 10)
- `double_chance_price` - Цена двойного шанса стать пидором (по умолчанию: 8)
- `prediction_price` - Цена создания предсказания (по умолчанию: 3)
- `reroll_price` - Цена перевыбора пидора дня (по умолчанию: 15)

**Награды (в пидоркоинах):**
- `coins_per_win` - Награда за победу в игре (по умолчанию: 4)
- `coins_per_command` - Награда за использование команды (по умолчанию: 1)
- `self_pidor_multiplier` - Множитель награды при самовыборе (по умолчанию: 2)
- `prediction_reward` - Награда за правильное предсказание (по умолчанию: 30)
- `give_coins_amount` - Количество койнов для раздачи обычным игрокам (по умолчанию: 1)
- `give_coins_winner_amount` - Количество койнов для раздачи победителю (по умолчанию: 2)

**Лимиты:**
- `max_missed_days_for_final_voting` - Максимальное количество пропущенных дней для финального голосования (по умолчанию: 10)
- `immunity_cooldown_days` - Период ожидания между покупками защиты в днях (по умолчанию: 7)
- `transfer_min_amount` - Минимальная сумма для перевода койнов (по умолчанию: 2)

**Таймауты:**
- `game_result_time_delay` - Задержка перед показом результата игры в секундах (по умолчанию: 2)
- `reroll_timeout_minutes` - Время действия кнопки перевыбора в минутах (по умолчанию: 5)

**Feature flags (включение/отключение функций):**
- `reroll_enabled` - Включить функцию перевыбора пидора (по умолчанию: true)
- `transfer_enabled` - Включить функцию перевода койнов между игроками (по умолчанию: true)
- `prediction_enabled` - Включить функцию предсказаний (по умолчанию: true)
- `immunity_enabled` - Включить функцию защиты от выбора (по умолчанию: true)
- `double_chance_enabled` - Включить функцию двойного шанса (по умолчанию: true)
- `give_coins_enabled` - Включить функцию раздачи койнов (по умолчанию: true)

#### Примеры использования

**Пример 1: Отключить перевыборы для конкретного чата**
```json
{
  "enabled_chats": [-123456],
  "chat_overrides": {
    "-123456": {
      "reroll_enabled": false
    }
  }
}
```

**Пример 2: Установить специальные цены для тестового чата**
```json
{
  "enabled_chats": [-123456, -789012],
  "test_chat_id": -789012,
  "chat_overrides": {
    "-789012": {
      "immunity_price": 1,
      "double_chance_price": 1,
      "prediction_price": 1,
      "reroll_price": 1
    }
  }
}
```

**Пример 3: Отключить все функции магазина для чата**
```json
{
  "enabled_chats": [-123456],
  "chat_overrides": {
    "-123456": {
      "reroll_enabled": false,
      "transfer_enabled": false,
      "prediction_enabled": false,
      "immunity_enabled": false,
      "double_chance_enabled": false,
      "give_coins_enabled": false
    }
  }
}
```

**Пример 4: Добавить новый чат с дефолтными настройками**
```json
{
  "enabled_chats": [-123456, -789012, -999999],
  "test_chat_id": -789012
}
```

#### Миграция со старой конфигурации

Если вы использовали переменные окружения `CHAT_WHITELIST` и `TEST_CHAT_ID`, создайте файл конфигурации:

**Было:**
```bash
export CHAT_WHITELIST="-1001392307997,-4608252738,-1002189152002"
export TEST_CHAT_ID="-4608252738"
```

**Стало:**
```bash
export GAME_CONFIG="/path/to/game_config.json"
```

**Содержимое game_config.json:**
```json
{
  "enabled_chats": [-1001392307997, -4608252738, -1002189152002],
  "test_chat_id": -4608252738
}
```

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
