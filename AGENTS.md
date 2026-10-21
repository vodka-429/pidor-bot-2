# AGENTS.md — Pidor Bot

Telegram-бот «пидор дня» с экономикой пидор-койнов. Python, python-telegram-bot (async), SQLModel + PostgreSQL, alembic. Деплой — GitOps: merge в `main` → CI собирает образ → ArgoCD на vdsina1.

## Неочевидное

- **Python:** прод — 3.13, CI-тесты — 3.10. Синтаксис и stdlib — не новее 3.10.
- **Боевой конфиг чатов** — `gameConfig` в `deploy/charts/app/values.yaml`. Его правка после merge сразу меняет прод. Версию образа в `values*.yaml` ведёт CI — не трогай.
- **Меню команд Telegram** — `bot/setup_commands.py` (выполняется при деплое). `docs/commands.txt` устарел.
- **Тесты без Postgres:** моки из `tests/conftest.py` или in-memory SQLite (пример — `tests/handlers/game/test_draw_schedule.py`). Время — через `current_datetime()` и моки, не хардкоженные даты.
- **CI коммитит в `main`** bump образа после каждого merge → перед push: `git fetch origin main && git rebase origin/main`.

## Чеклист изменения

- Модели (`bot/app/models.py`) → миграция в `migrations/versions/`, `down_revision` = текущий head, head остаётся один. Применяется сама при деплое.
- Новая команда → `bot/dispatcher.py` + `bot/setup_commands.py`.
- Новый параметр или флаг → поле с docstring в `GameConstants` (`bot/handlers/game/config.py`) + `game_config.example.json`. Новая фича по умолчанию выключена и включается через `chat_overrides`, сначала в тестовом чате `-1003932067905`.
- Заметная для игроков фича → «Новые функции» в `README.md`.
- Экономика койнов → `vibe/pidorcoins-economy.md`: механика и статус фичи (IDEA → PILOT → RELEASED). Историю изменений туда не пиши — она в git и PR.
- Анонс в `/pidornews` (`changelog_service.py`) — только по решению человека.
- Тесты на новую логику обязательны.

## Правила

- Ответы — на русском; коммиты и PR — на английском, conventional commits.
- Если у тебя установлен скилл или стиль `pohuy` — используй его в чате всегда, с первого ответа. Нет — отвечай обычно, ничего не ищи и не ставь. Код, комментарии, тексты бота, коммиты, PR и доки — без мата в любом случае.
- Работа — в ветке `feat/<слаг>` или `fix/<слаг>` от `origin/main`; в `main` не коммитить.
- Merge PR — только человек: это и есть деплой. Инфраструктуру (k8s, helm, terraform, ansible, ручные миграции) агенты не трогают.
