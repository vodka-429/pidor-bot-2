# CLAUDE.md — контекст проекта Pidor Bot

Telegram-бот «пидор дня»: ежедневный розыгрыш в чатах, экономика пидор-койнов (магазин, переводы, тотализатор, достижения), финальное голосование в конце года. PostgreSQL, деплой GitOps в K8s на vdsina1.

Этот файл — общий контекст для всех агентов (включая субагентов, которые стартуют «холодными»). Держи его актуальным.

## Стек

- **Bot:** python-telegram-bot 22.8 (async), SQLModel/SQLAlchemy 2, psycopg
- **DB:** PostgreSQL; модели — `bot/app/models.py`; миграции — alembic (`migrations/versions/`)
- **Python:** прод — 3.13 (`Dockerfile`, `runtime.txt`), CI-тесты — 3.10. Код должен работать на обоих: не используй синтаксис/stdlib новее 3.10.
- **Infra:** GitHub Actions → GHCR (`ghcr.io/vodka-429/pidor-bot-2`) → ArgoCD (app `pidor-2`, namespace `pidor`, Helm-чарт `deploy/charts/app/`)

## Карта кода

- `main.py` — запуск, polling, watchdog; `bot/dispatcher.py` — регистрация всех хендлеров
- `bot/handlers/game/commands.py` — основные игровые команды (`/pidor`, `/pidoreg`, `/pidorstats`, финальное голосование…); декоратор `ensure_game`
- `bot/handlers/game/*_service.py` — бизнес-логика по фичам (shop, transfer, totalizator, reroll, prediction, toast, achievements, draw_schedule, economy_pilot, changelog…)
- `bot/handlers/game/config.py` — `GameConstants` (цены, награды, лимиты, **feature flags**) + загрузка per-chat конфига
- `bot/handlers/game/phrases/`, `text_static.py` — тексты бота
- `bot/setup_commands.py` — список команд для меню Telegram (выполняется при деплое). `docs/commands.txt` устарел — не ориентируйся на него.
- `tests/` — pytest; общие фикстуры — `tests/conftest.py`

## Конфигурация чатов

- Боевой конфиг — `gameConfig` в `deploy/charts/app/values.yaml` (→ ConfigMap → `GAME_CONFIG_PATH`). **Его правка = изменение прода после merge.**
- Новый параметр добавляется в три места: поле + docstring в `GameConstants`, `game_config.example.json`, при необходимости — `values.yaml`.
- Новая пользовательская фича по умолчанию **выключена** (`*_enabled: False`) и включается через `chat_overrides` — сначала в тестовом чате `-1003932067905`.
- Образ в `values.yaml`/`values-vdsina1.yaml` не трогай — версию ведёт CI.

## Тесты (критерий «не сломал»)

```bash
pytest                                   # всё; coverage включён в pytest.ini, нужен pytest-cov
pytest tests/handlers/game/test_shop_service.py -q   # точечно
```

Postgres не нужен: тесты на моках (`tests/conftest.py`) и на in-memory SQLite (`create_engine('sqlite://')` + `SQLModel.metadata.create_all`). Логику с БД тестируй вторым способом (пример — `tests/handlers/game/test_draw_schedule.py`).

**Тесты на новую логику обязательны.** Время — через `current_datetime()`/моки, а не хардкоженные даты, которые «протухают».

## Чеклист изменения (смотри, что применимо)

- [ ] Новая таблица/колонка → модель в `bot/app/models.py` + миграция в `migrations/versions/` с `down_revision` = текущий head (у alembic должен остаться **один head**). Миграции применяются автоматически при деплое (helm hook `db-init`).
- [ ] Новая команда → хендлер в `bot/dispatcher.py` + строка в `bot/setup_commands.py`.
- [ ] Новый параметр/флаг → см. «Конфигурация чатов».
- [ ] Заметная фича для игроков → раздел «Новые функции» в `README.md`.
- [ ] Изменение экономики койнов → `vibe/pidorcoins-economy.md` (статус фичи + запись в «Историю изменений» со следующей версией vN).
- [ ] Анонс в чатах (`/pidornews`, `bot/handlers/game/changelog_service.py`) — **только по решению человека**, для крупных релизов.
- [ ] Новая зависимость → `requirements.txt` (с пином версии).

## Правила работы

- Ответы и планы — на русском. Коммиты и PR — на английском, conventional commits: `feat: …`, `fix: …`, `chore: …`, `docs: …`.
- Работа — в фиче-ветке `feat/<слаг>` / `fix/<слаг>` от свежего `origin/main`. В `main` не коммить (pre-commit `no-commit-to-branch`).
- CI после каждого merge коммитит в `main` bump `values-vdsina1.yaml` → перед push всегда `git fetch origin main && git rebase origin/main`.

## Деплой и границы (важно для агентов)

- Деплой **только через GitOps**: merge PR в `main` → CI собирает образ → ArgoCD (selfHeal, prune). Гейт — **человек мёржит PR**.
- Агентам запрещено: мутации `kubectl`/`helm`, `terraform apply` (`deploy/yc_tf/`), `ansible-playbook` (`ansible/` — legacy), `alembic upgrade/downgrade` вручную, push в `main`, force-push.
- Не трогай секреты (`deploy/argocd/secrets.yaml`, `.env`).

## Мультиагентная разработка

Роли в `.claude/agents/`: `architect` (read-only план), `coder` (код + тесты + коммит), `reviewer` (независимая проверка, без правок). Оркестрация — команда `/feature <задача>`: ветка → план → вопросы человеку → код → ревью → PR. Merge — за человеком.

`.claude/settings.json`: `defaultMode: acceptEdits`, безопасные команды в allow, опасные — в deny (deny приоритетнее режима и allow).
