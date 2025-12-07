# Fake sublime telegram bot sources

![Tests](https://github.com/vodka-429/pidor-bot-2/actions/workflows/tests.yml/badge.svg)

This is _FAKE_ sources just **_imitating_** the functionality similar to the one by SublimeBot in Telegram

## Prerequisites

* (Optionally) Install Python 3.8 and/or Docker
* Create `.env` file and put `TELEGRAM_BOT_API_TOKEN=<token>` there

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
