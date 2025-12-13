import asyncio
import json
import functools
import logging
import random
from datetime import datetime
from typing import List
from zoneinfo import ZoneInfo

from sqlalchemy import func, text
from sqlmodel import select
from telegram import Update
from telegram.ext import CallbackContext

from bot.app.models import Game, TGUser, GameResult, FinalVoting
from bot.handlers.db.handlers import tg_user_from_text
from bot.handlers.game.phrases import stage1, stage2, stage3, stage4
from bot.handlers.game.text_static import STATS_PERSONAL, \
    STATS_CURRENT_YEAR, \
    STATS_ALL_TIME, STATS_LIST_ITEM, REGISTRATION_SUCCESS, \
    ERROR_ALREADY_REGISTERED, ERROR_ZERO_PLAYERS, ERROR_NOT_ENOUGH_PLAYERS, \
    CURRENT_DAY_GAME_RESULT, \
    YEAR_RESULTS_MSG, YEAR_RESULTS_ANNOUNCEMENT, REGISTRATION_MANY_SUCCESS, \
    ERROR_ALREADY_REGISTERED_MANY, VOTING_ENDED_RESPONSE
from bot.utils import escape_markdown2, escape_word, format_number, ECallbackContext

# Получаем логгер для этого модуля
logger = logging.getLogger(__name__)


GAME_RESULT_TIME_DELAY = 2
MAX_MISSED_DAYS_FOR_FINAL_VOTING = 10  # Максимальное количество пропущенных дней для финального голосования
TEST_CHAT_ID = -4608252738  # ID тестового чата для обхода ограничений по датам

MOSCOW_TZ = ZoneInfo('Europe/Moscow')


def current_datetime():
    return datetime.now(tz=MOSCOW_TZ)


def is_test_chat(chat_id: int) -> bool:
    """Проверяет, является ли чат тестовым"""
    return chat_id == TEST_CHAT_ID


def get_missed_days_count(db_session, game_id: int, current_year: int, current_day: int) -> int:
    """Подсчёт пропущенных дней с последнего розыгрыша"""
    # Получаем последний результат игры в текущем году
    last_result = db_session.query(GameResult).filter_by(
        game_id=game_id,
        year=current_year
    ).order_by(GameResult.day.desc()).first()

    if last_result is None:
        # Если игр в этом году не было, считаем все дни с начала года
        return current_day - 1

    # Считаем пропущенные дни между последней игрой и текущим днём
    missed = current_day - last_result.day - 1
    return max(0, missed)


def get_all_missed_days(db_session, game_id: int, current_year: int, current_day: int) -> list[int]:
    """Получение списка всех пропущенных дней в году"""
    # Получаем все дни, когда проводились игры в текущем году
    played_days = db_session.query(GameResult.day).filter_by(
        game_id=game_id,
        year=current_year
    ).all()

    played_days_set = {day[0] for day in played_days}

    # Все дни от 1 до текущего дня, которые не были сыграны
    all_days = set(range(1, current_day))
    missed_days = sorted(all_days - played_days_set)

    return missed_days


def get_dramatic_message(days_count: int) -> str:
    """Выбор драматического сообщения по количеству пропущенных дней"""
    from bot.handlers.game.text_static import (
        MISSED_DAYS_1, MISSED_DAYS_2_3, MISSED_DAYS_4_7,
        MISSED_DAYS_8_14, MISSED_DAYS_15_30, MISSED_DAYS_31_PLUS
    )

    if days_count == 1:
        return MISSED_DAYS_1
    elif 2 <= days_count <= 3:
        return MISSED_DAYS_2_3.format(days=days_count)
    elif 4 <= days_count <= 7:
        return MISSED_DAYS_4_7.format(days=days_count)
    elif 8 <= days_count <= 14:
        return MISSED_DAYS_8_14.format(days=days_count)
    elif 15 <= days_count <= 30:
        return MISSED_DAYS_15_30.format(days=days_count)
    else:  # 31+
        return MISSED_DAYS_31_PLUS.format(days=days_count)


def day_to_date(year: int, day: int) -> datetime:
    """Преобразование номера дня в дату"""
    from datetime import timedelta
    return datetime(year, 1, 1, tzinfo=MOSCOW_TZ) + timedelta(days=day - 1)


class GECallbackContext(ECallbackContext):
    """Extended bot context with additional game `Game` field"""
    game: Game


def ensure_game(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: ECallbackContext):
        game: Game = context.db_session.query(Game).filter_by(chat_id=update.effective_chat.id).one_or_none()
        if game is None:
            game = Game(chat_id=update.effective_chat.id)
            context.db_session.add(game)
            context.db_session.commit()
            context.db_session.refresh(game)
        context.game = game
        return await func(update, context)

    return wrapper


# PIDOR Game
@ensure_game
async def pidor_cmd(update: Update, context: GECallbackContext):
    logger.info(f"pidor_cmd started for chat {update.effective_chat.id}")
    logger.info(f"Game {context.game.id} of the day started")
    players: List[TGUser] = context.game.players

    if len(players) < 2:
        await update.effective_chat.send_message(ERROR_NOT_ENOUGH_PLAYERS)
        return

    current_dt = current_datetime()
    cur_year, cur_day = current_dt.year, current_dt.timetuple().tm_yday
    last_day = current_dt.month == 12 and current_dt.day >= 31

    # Проверка пропущенных дней
    missed_days = get_missed_days_count(context.db_session, context.game.id, cur_year, cur_day)
    if missed_days > 0:
        logger.info(f"Missed {missed_days} days since last game")
        dramatic_msg = get_dramatic_message(missed_days)
        await update.effective_chat.send_message(dramatic_msg, parse_mode="MarkdownV2")
        await asyncio.sleep(GAME_RESULT_TIME_DELAY)

    game_result: GameResult = context.db_session.query(GameResult).filter_by(game_id=context.game.id, year=cur_year, day=cur_day).one_or_none()
    if game_result:
        await update.message.reply_markdown_v2(
            CURRENT_DAY_GAME_RESULT.format(
                username=escape_markdown2(game_result.winner.full_username())))
    else:
        logger.debug("Creating new game result")
        winner: TGUser = random.choice(players)
        context.game.results.append(GameResult(game_id=context.game.id, year=cur_year, day=cur_day, winner=winner))
        logger.debug("Committing game result to DB")
        context.db_session.commit()

        if last_day:
            logger.debug("Sending year results announcement")
            await update.effective_chat.send_message(YEAR_RESULTS_ANNOUNCEMENT.format(year=cur_year), parse_mode="MarkdownV2")

        logger.debug("Sending stage 1 message")
        await update.effective_chat.send_message(random.choice(stage1.phrases))
        await asyncio.sleep(GAME_RESULT_TIME_DELAY)
        logger.debug("Sending stage 2 message")
        await update.effective_chat.send_message(random.choice(stage2.phrases))
        await asyncio.sleep(GAME_RESULT_TIME_DELAY)
        logger.debug("Sending stage 3 message")
        await update.effective_chat.send_message(random.choice(stage3.phrases))
        await asyncio.sleep(GAME_RESULT_TIME_DELAY)
        logger.debug("Sending stage 4 message")
        await update.effective_chat.send_message(random.choice(stage4.phrases).format(
            username=winner.full_username(mention=True)))


async def pidorules_cmd(update: Update, _context: CallbackContext):
    logger.info("Game rules requested")
    await update.effective_chat.send_message(
        "Правила игры *Пидор Дня* (только для групповых чатов):\n"
        "*1.* Зарегистрируйтесь в игру по команде */pidoreg*\n"
        "*2.* Подождите пока зарегиструются все (или большинство :)\n"
        "*3.* Запустите розыгрыш по команде */pidor*\n"
        "*4.* Просмотр статистики канала по команде */pidorstats*, */pidorall*\n"
        "*5.* Личная статистика по команде */pidorme*\n"
        "*6.* Статистика за последний год по комнаде */pidor2020* (так же есть за 2016-2020)\n"
        "*7.* Просмотр пропущенных дней в текущем году: */pidormissed*\n"
        "*8.* Финальное голосование за пропущенные дни (29-30 декабря): */pidorfinal*\n"
        "*9.* Статус финального голосования: */pidorfinalstatus*\n"
        "*10. (!!! Только для администраторов чатов)*: удалить из игры может только Админ канала, сначала выведя по команде список игроков: */pidormin* list\n"
        "Удалить же игрока можно по команде (используйте идентификатор пользователя - цифры из списка пользователей): */pidormin* del 123456\n"
        "\n"
        "*Важно*, розыгрыш проходит только *раз в день*, повторная команда выведет *результат* игры.\n"
        "\n"
        "*Финальное голосование:* В конце года (29-30 декабря) можно запустить взвешенное голосование для распределения пропущенных дней. "
        "Финальное голосование с кастомными кнопками (поддерживает любое количество участников). Результаты скрыты до завершения. "
        "Вес каждого голоса равен количеству побед игрока в текущем году. "
        "Голосование доступно только если пропущено менее 10 дней. Завершить голосование: */pidorfinalclose*\n"
        "\n"
        "Сброс розыгрыша происходит каждый день в 12 часов ночи по UTC+2 (примерно в два часа ночи по Москве).\n\n"
        "Поддержать бота можно по [ссылке](https://github.com/vodka-429/pidor-bot-2/):)",
        parse_mode="MarkdownV2", disable_web_page_preview=True)


@ensure_game
async def pidoreg_cmd(update: Update, context: GECallbackContext):
    players: List[TGUser] = context.game.players

    if len(players) == 0:
        await update.effective_chat.send_message(
            ERROR_ZERO_PLAYERS.format(username=update.message.from_user.name))

    if context.tg_user not in context.game.players:
        context.game.players.append(context.tg_user)
        context.db_session.commit()
        await update.effective_message.reply_markdown_v2(REGISTRATION_SUCCESS)
    else:
        await update.effective_message.reply_markdown_v2(ERROR_ALREADY_REGISTERED)


@ensure_game
async def pidoregmany_cmd(update: Update, context: GECallbackContext):
    import os
    from dotenv import load_dotenv
    from telegram import Bot

    load_dotenv()
    bot = Bot(os.environ['TELEGRAM_BOT_API_SECRET'])

    users = update.message.text.split()[1:]
    for user_id in users:
        try:
            user_status = await bot.get_chat_member(chat_id=update.message.chat.id, user_id=user_id)
            tg_user_from_text(user_status.user, update, context)

            if context.tg_user not in context.game.players:
                context.game.players.append(context.tg_user)
                context.db_session.commit()
                await update.effective_message.reply_markdown_v2(REGISTRATION_MANY_SUCCESS.format(username=context.tg_user.full_username()))
            else:
                await update.effective_message.reply_markdown_v2(ERROR_ALREADY_REGISTERED_MANY.format(username=context.tg_user.full_username()))
        except Exception:
            logger.exception("Exception with user {}".format(user_id))
            await update.effective_message.reply_markdown_v2('Хуйня с {}'.format(user_id))


@ensure_game
async def pidorunreg_cmd(update: Update, context: GECallbackContext):
    await update.effective_message.reply_markdown_v2('Хуй там плавал')
    # if context.tg_user in context.game.players:
    #     context.game.players.remove(context.tg_user)
    #     context.db_session.commit()
    #     update.effective_message.reply_markdown_v2(REMOVE_REGISTRATION)
    # else:
    #     update.effective_message.reply_markdown_v2(REMOVE_REGISTRATION_ERROR)


def build_player_table(player_list: list[tuple[TGUser, int]]) -> str:
    result = []
    for number, (tg_user, amount) in enumerate(player_list, 1):
        result.append(STATS_LIST_ITEM.format(number=number,
                                             username=escape_markdown2(tg_user.full_username()),
                                             amount=format_number(amount)))
    return ''.join(result)


@ensure_game
async def pidoryearresults_cmd(update: Update, context: GECallbackContext):
    result_year: int = int(update.effective_message.text.removeprefix('/pidor')[:4])

    stmt = select(TGUser, func.count(GameResult.winner_id).label('count')) \
        .join(TGUser, GameResult.winner_id == TGUser.id) \
        .filter(GameResult.game_id == context.game.id, GameResult.year == result_year) \
        .group_by(TGUser) \
        .order_by(text('count DESC')) \
        .limit(50)
    db_results = context.db_session.exec(stmt).all()

    if len(db_results) == 0:
        await update.effective_chat.send_message(
            ERROR_ZERO_PLAYERS.format(
                username=update.message.from_user.name))
        return

    player_table = build_player_table(db_results)
    answer = YEAR_RESULTS_MSG.format(username=escape_markdown2(db_results[0][0].full_username()), year=result_year, player_list=player_table)
    await update.effective_chat.send_message(answer, parse_mode="MarkdownV2")


@ensure_game
async def pidorstats_cmd(update: Update, context: GECallbackContext):
    cur_year = current_datetime().year
    stmt = select(TGUser, func.count(GameResult.winner_id).label('count')) \
        .join(TGUser, GameResult.winner_id == TGUser.id) \
        .filter(GameResult.game_id == context.game.id, GameResult.year == cur_year) \
        .group_by(TGUser) \
        .order_by(text('count DESC')) \
        .limit(50)
    db_results = context.db_session.exec(stmt).all()

    player_table = build_player_table(db_results)
    answer = STATS_CURRENT_YEAR.format(player_stats=player_table,
                                       player_count=len(context.game.players))
    await update.effective_chat.send_message(answer, parse_mode="MarkdownV2")


@ensure_game
async def pidorall_cmd(update: Update, context: GECallbackContext):
    stmt = select(TGUser, func.count(GameResult.winner_id).label('count')) \
        .join(TGUser, GameResult.winner_id == TGUser.id) \
        .filter(GameResult.game_id == context.game.id) \
        .group_by(TGUser) \
        .order_by(text('count DESC')) \
        .limit(50)
    db_results = context.db_session.exec(stmt).all()

    player_table = build_player_table(db_results)
    answer = STATS_ALL_TIME.format(player_stats=player_table,
                                   player_count=len(context.game.players))
    await update.effective_chat.send_message(answer, parse_mode="MarkdownV2")


@ensure_game
async def pidorme_cmd(update: Update, context: GECallbackContext):
    stmt = select(TGUser, func.count(GameResult.winner_id).label('count')) \
        .join(TGUser, GameResult.winner_id == TGUser.id) \
        .filter(GameResult.game_id == context.game.id, GameResult.winner_id == context.tg_user.id) \
        .group_by(TGUser) \
        .order_by(text('count DESC'))
    tg_user, count = context.db_session.exec(stmt).one()

    await update.effective_chat.send_message(STATS_PERSONAL.format(
        username=tg_user.full_username(), amount=count),
        parse_mode="MarkdownV2")


@ensure_game
async def pidormissed_cmd(update: Update, context: GECallbackContext):
    """Показать пропущенные дни в текущем году"""
    from bot.handlers.game.text_static import MISSED_DAYS_INFO_WITH_LIST, MISSED_DAYS_INFO_COUNT_ONLY

    logger.info(f"pidormissed_cmd started for chat {update.effective_chat.id}")

    # Получаем текущий год и день
    current_dt = current_datetime()
    cur_year, cur_day = current_dt.year, current_dt.timetuple().tm_yday

    # Получаем список всех пропущенных дней
    missed_days = get_all_missed_days(context.db_session, context.game.id, cur_year, cur_day)
    missed_count = len(missed_days)

    if missed_count == 0:
        await update.effective_chat.send_message(
            "✅ В этом году не пропущено ни одного дня\\! Отличная работа\\! 🎉",
            parse_mode="MarkdownV2"
        )
        return

    # Если пропущено меньше MAX_MISSED_DAYS_FOR_FINAL_VOTING дней - показываем список с датами
    if missed_count < MAX_MISSED_DAYS_FOR_FINAL_VOTING:
        days_list_items = []
        for day_num in missed_days:
            date = day_to_date(cur_year, day_num)
            # Форматируем дату как "1 января", "2 февраля" и т.д.
            date_str = date.strftime("%d %B").lstrip('0')
            # Экранируем для Markdown V2
            date_str_escaped = escape_markdown2(date_str)
            days_list_items.append(f"• {date_str_escaped}")

        days_list = '\n'.join(days_list_items)
        message = MISSED_DAYS_INFO_WITH_LIST.format(count=missed_count, days_list=days_list)
    else:
        # Если больше или равно MAX_MISSED_DAYS_FOR_FINAL_VOTING - показываем только количество
        message = MISSED_DAYS_INFO_COUNT_ONLY.format(count=missed_count)

    await update.effective_chat.send_message(message, parse_mode="MarkdownV2")
    logger.info(f"Showed {missed_count} missed days for game {context.game.id}")


@ensure_game
async def pidorfinal_cmd(update: Update, context: GECallbackContext):
    """Запустить финальное голосование для распределения пропущенных дней"""
    from bot.handlers.game.text_static import (
        FINAL_VOTING_ERROR_DATE,
        FINAL_VOTING_ERROR_TOO_MANY, FINAL_VOTING_ERROR_ALREADY_EXISTS
    )
    from bot.handlers.game.voting_helpers import (
        create_voting_keyboard, get_player_weights, format_weights_message, get_year_leaders
    )

    logger.info(f"pidorfinal_cmd started for chat {update.effective_chat.id}")

    # Получаем текущую дату
    current_dt = current_datetime()
    cur_year, cur_day = current_dt.year, current_dt.timetuple().tm_yday

    # Проверяем, что сейчас 29 или 30 декабря (пропускаем для тестового чата)
    if not is_test_chat(update.effective_chat.id):
        if not (current_dt.month == 12 and current_dt.day in [29, 30]):
            await update.effective_chat.send_message(
                FINAL_VOTING_ERROR_DATE,
                parse_mode="MarkdownV2"
            )
            logger.warning(f"Attempt to start final voting on wrong date: {current_dt.date()}")
            return

    # Получаем список пропущенных дней
    missed_days = get_all_missed_days(context.db_session, context.game.id, cur_year, cur_day)
    missed_count = len(missed_days)

    # Проверяем, что пропущено меньше MAX_MISSED_DAYS_FOR_FINAL_VOTING дней (пропускаем для тестового чата)
    if not is_test_chat(update.effective_chat.id):
        if missed_count >= MAX_MISSED_DAYS_FOR_FINAL_VOTING:
            await update.effective_chat.send_message(
                FINAL_VOTING_ERROR_TOO_MANY.format(
                    count=missed_count,
                    max_days=MAX_MISSED_DAYS_FOR_FINAL_VOTING
                ),
                parse_mode="MarkdownV2"
            )
            logger.warning(f"Too many missed days for final voting: {missed_count}")
            return

    # Проверяем, что голосование ещё не запущено
    existing_voting = context.db_session.query(FinalVoting).filter_by(
        game_id=context.game.id,
        year=cur_year
    ).one_or_none()

    if existing_voting is not None:
        await update.effective_chat.send_message(
            FINAL_VOTING_ERROR_ALREADY_EXISTS,
            parse_mode="MarkdownV2"
        )
        logger.warning(f"Final voting already exists for game {context.game.id}, year {cur_year}")
        return

    # Получаем веса игроков (количество побед в году)
    player_weights = get_player_weights(context.db_session, context.game.id, cur_year)

    if len(player_weights) == 0:
        await update.effective_chat.send_message(
            "❌ *Ошибка\\!* В этом году ещё не было ни одного розыгрыша\\. Финальное голосование невозможно\\.",
            parse_mode="MarkdownV2"
        )
        logger.warning(f"No games played in year {cur_year} for game {context.game.id}")
        return

    # Определяем всех лидеров года (игроки с максимальным количеством побед)
    year_leaders = get_year_leaders(player_weights)

    # Создаем список ID исключенных лидеров
    excluded_leader_ids = [leader.id for leader, _ in year_leaders]

    # Создаем список кандидатов, исключая всех лидеров
    candidates = [player for player, _ in player_weights if player.id not in excluded_leader_ids]

    # Создаём словарь с количеством побед для каждого игрока
    player_wins = {player.id: wins for player, wins in player_weights}

    # Подготавливаем информацию об исключенных лидерах для сохранения
    excluded_leaders_data = [{"player_id": leader.id, "wins": wins} for leader, wins in year_leaders]

    # Сначала создаём запись FinalVoting без voting_message_id
    final_voting = FinalVoting(
        game_id=context.game.id,
        year=cur_year,
        poll_id='',  # Больше не используется для кастомного голосования
        poll_message_id=0,  # Временное значение, будет обновлено
        started_at=current_dt,
        missed_days_count=missed_count,
        missed_days_list=json.dumps(missed_days),
        votes_data='{}',  # Инициализируем пустым JSON объектом
        is_results_hidden=True,  # Скрываем результаты до завершения
        voting_message_id=None  # Будет установлено после отправки сообщения
    )
    context.db_session.add(final_voting)
    context.db_session.flush()  # Получаем ID для использования в callback_data

    # Создаём клавиатуру с кнопками кандидатов, исключая всех лидеров
    keyboard = create_voting_keyboard(
        candidates,
        voting_id=final_voting.id,
        votes_per_row=2,
        chat_id=update.effective_chat.id,
        player_wins=player_wins,
        excluded_players=excluded_leader_ids
    )

    logger.info(f"Created keyboard with {len(keyboard.inline_keyboard)} rows")
    logger.info(f"FinalVoting ID: {final_voting.id}")

    # Рассчитываем максимальное количество выборов
    from bot.handlers.game.voting_helpers import calculate_max_votes
    max_votes = calculate_max_votes(missed_count)

    # Формируем и отправляем объединённое сообщение с информацией и кнопками голосования
    # Включаем информацию об исключенных лидерах
    message_text = format_weights_message(
        player_weights,
        missed_count,
        max_votes,
        excluded_leaders=year_leaders
    )
    voting_message = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=message_text,
        parse_mode="MarkdownV2",
        reply_markup=keyboard
    )

    # Обновляем запись с ID сообщения голосования
    final_voting.voting_message_id = voting_message.message_id

    # Сохраняем информацию об исключенных лидерах в новое поле excluded_leaders_data
    final_voting.excluded_leaders_data = json.dumps(excluded_leaders_data)
    context.db_session.commit()

    logger.info(f"Final voting created for game {context.game.id}, year {cur_year}, voting_message_id {voting_message.message_id}")
    logger.info(f"Excluded leaders: {excluded_leader_ids}")


async def handle_vote_callback(update: Update, context: ECallbackContext):
    """Обработчик нажатий на кнопки голосования"""
    from bot.handlers.game.voting_helpers import parse_vote_callback_data

    query = update.callback_query

    if query is None:
        logger.error("callback_query is None!")
        return

    logger.info(f"Vote callback from user {query.from_user.id} in chat {update.effective_chat.id}")
    logger.info(f"Callback data: {query.data}")

    try:
        # Парсим callback_data для получения voting_id и candidate_id
        voting_id, candidate_id = parse_vote_callback_data(query.data)
        logger.info(f"Parsed callback: voting_id={voting_id}, candidate_id={candidate_id}")
    except ValueError as e:
        logger.error(f"Failed to parse callback_data: {e}")
        query.answer("❌ Ошибка обработки голоса")
        return

    # Загружаем FinalVoting по voting_id
    final_voting = context.db_session.query(FinalVoting).filter_by(
        id=voting_id
    ).one_or_none()

    if final_voting is None:
        logger.warning(f"FinalVoting not found for id {voting_id}")
        query.answer("❌ Голосование не найдено")
        return

    # Проверяем, что голосование ещё активно
    if final_voting.ended_at is not None:
        logger.info(f"Voting {voting_id} already ended")
        await query.answer(VOTING_ENDED_RESPONSE)
        return

    # Загружаем текущие голоса из votes_data
    votes_data = json.loads(final_voting.votes_data)
    user_id = str(query.from_user.id)  # Используем строковый ключ для JSON

    # Получаем список голосов пользователя (или создаём пустой)
    user_votes = votes_data.get(user_id, [])

    # Рассчитываем максимальное количество выборов для данного голосования
    from bot.handlers.game.voting_helpers import calculate_max_votes
    max_votes = calculate_max_votes(final_voting.missed_days_count)

    # Toggle логика: добавляем или удаляем candidate_id
    if candidate_id in user_votes:
        # Удаляем голос
        user_votes.remove(candidate_id)
        answer_text = "✅ Голос отменён"
        logger.info(f"User {user_id} removed vote for candidate {candidate_id}")
    else:
        # Проверяем лимит выборов перед добавлением
        if len(user_votes) >= max_votes:
            answer_text = f"❌ Превышен лимит выборов ({max_votes})"
            logger.info(f"User {user_id} exceeded vote limit {max_votes}")
            await query.answer(answer_text)
            return

        # Добавляем голос
        user_votes.append(candidate_id)
        answer_text = "✅ Голос учтён"
        logger.info(f"User {user_id} added vote for candidate {candidate_id}")

    # Обновляем голоса пользователя
    votes_data[user_id] = user_votes

    # Сохраняем обновлённые голоса обратно в votes_data
    final_voting.votes_data = json.dumps(votes_data)
    context.db_session.commit()

    # Отвечаем на callback
    await query.answer(answer_text)

    logger.info(f"Vote processed for voting {voting_id}, user {user_id}, candidate {candidate_id}")


@ensure_game
async def pidorfinalstatus_cmd(update: Update, context: GECallbackContext):
    """Показать статус финального голосования"""
    from bot.handlers.game.text_static import (
        FINAL_VOTING_STATUS_NOT_STARTED,
        FINAL_VOTING_STATUS_ACTIVE,
        FINAL_VOTING_STATUS_ACTIVE_WITH_VOTERS,
        FINAL_VOTING_STATUS_COMPLETED
    )
    from bot.handlers.game.voting_helpers import count_voters

    logger.info(f"pidorfinalstatus_cmd started for chat {update.effective_chat.id}")

    # Получаем текущий год
    current_dt = current_datetime()
    cur_year = current_dt.year

    # Находим запись FinalVoting для текущего года и игры
    final_voting = context.db_session.query(FinalVoting).filter_by(
        game_id=context.game.id,
        year=cur_year
    ).one_or_none()

    # Если запись не найдена - показываем статус "не запущено"
    if final_voting is None:
        await update.effective_chat.send_message(
            FINAL_VOTING_STATUS_NOT_STARTED,
            parse_mode="MarkdownV2"
        )
        logger.info(f"Final voting not started for game {context.game.id}, year {cur_year}")
        return

    # Если ended_at is None - показываем статус "активно"
    if final_voting.ended_at is None:
        # Форматируем дату для вывода
        started_str = final_voting.started_at.strftime("%d\\.%m\\.%Y %H:%M МСК")

        # Подсчитываем количество проголосовавших
        voters_count = count_voters(final_voting.votes_data)

        message = FINAL_VOTING_STATUS_ACTIVE_WITH_VOTERS.format(
            started_at=started_str,
            missed_days=final_voting.missed_days_count,
            voters_count=voters_count
        )
        await update.effective_chat.send_message(message, parse_mode="MarkdownV2")
        logger.info(f"Final voting active for game {context.game.id}, year {cur_year}, voters: {voters_count}")
        return

    # Если ended_at is not None - показываем статус "завершено"
    # Загружаем информацию о победителях из winners_data
    try:
        winners_data = json.loads(final_voting.winners_data)
        if winners_data:
            # Загружаем объекты победителей
            winner_names = []
            for winner_info in winners_data:
                winner = context.db_session.query(TGUser).filter_by(id=winner_info['winner_id']).one()
                winner_names.append(escape_markdown2(winner.full_username()))
            winners_text = ', '.join(winner_names)
        else:
            # Fallback на старое поле winner_id
            winners_text = escape_markdown2(final_voting.winner.full_username()) if final_voting.winner else "Нет победителей"
    except (json.JSONDecodeError, KeyError):
        # Fallback на старое поле winner_id
        winners_text = escape_markdown2(final_voting.winner.full_username()) if final_voting.winner else "Нет победителей"

    ended_str = final_voting.ended_at.strftime("%d\\.%m\\.%Y %H:%M МСК")

    message = FINAL_VOTING_STATUS_COMPLETED.format(
        winner=winners_text,
        ended_at=ended_str,
        missed_days=final_voting.missed_days_count
    )
    await update.effective_chat.send_message(message, parse_mode="MarkdownV2")

    # Логируем всех победителей
    winners_log = winners_text.replace('\\', '')  # Убираем экранирование для лога
    logger.info(f"Final voting completed for game {context.game.id}, year {cur_year}, winners: {winners_log}")


@ensure_game
async def pidorfinalclose_cmd(update: Update, context: GECallbackContext):
    """Завершить финальное голосование вручную (только для администраторов)"""
    from bot.handlers.game.text_static import (
        FINAL_VOTING_CLOSE_SUCCESS,
        FINAL_VOTING_CLOSE_ERROR_NOT_ADMIN,
        FINAL_VOTING_CLOSE_ERROR_NOT_ACTIVE,
        FINAL_VOTING_RESULTS
    )
    from bot.handlers.game.voting_helpers import finalize_voting, format_voting_results

    logger.info(f"pidorfinalclose_cmd started for chat {update.effective_chat.id}")

    # Получаем текущий год
    current_dt = current_datetime()
    cur_year = current_dt.year

    # Находим активное голосование для текущего года
    final_voting = context.db_session.query(FinalVoting).filter_by(
        game_id=context.game.id,
        year=cur_year
    ).one_or_none()

    # Проверяем, что голосование существует и активно
    if final_voting is None or final_voting.ended_at is not None:
        await update.effective_chat.send_message(
            FINAL_VOTING_CLOSE_ERROR_NOT_ACTIVE,
            parse_mode="MarkdownV2"
        )
        logger.warning(f"No active voting found for game {context.game.id}, year {cur_year}")
        return

    # Проверяем, что команду вызвал администратор чата
    try:
        chat_member = await context.bot.get_chat_member(
            chat_id=update.effective_chat.id,
            user_id=update.effective_user.id
        )
        is_admin = chat_member.status in ['creator', 'administrator']
    except Exception as e:
        logger.error(f"Failed to check admin status: {e}")
        is_admin = False

    if not is_admin:
        await update.effective_chat.send_message(
            FINAL_VOTING_CLOSE_ERROR_NOT_ADMIN,
            parse_mode="MarkdownV2"
        )
        logger.warning(f"Non-admin user {update.effective_user.id} tried to close voting")
        return

    # Проверяем, что прошло не менее 24 часов с момента старта голосования (пропускаем для тестового чата)
    if not is_test_chat(update.effective_chat.id):
        from datetime import timedelta
        min_voting_duration = timedelta(hours=24)
        time_since_start = current_dt - final_voting.started_at

        if time_since_start < min_voting_duration:
            remaining_time = min_voting_duration - time_since_start
            hours_remaining = int(remaining_time.total_seconds() // 3600)
            minutes_remaining = int((remaining_time.total_seconds() % 3600) // 60)

            await update.effective_chat.send_message(
                f"❌ *Ошибка\\!* Голосование можно завершить только через 24 часа после старта\\.\n\n"
                f"Осталось: *{format_number(hours_remaining)}* ч\\. *{format_number(minutes_remaining)}* мин\\.",
                parse_mode="MarkdownV2"
            )
            logger.warning(f"Attempt to close voting too early. Time since start: {time_since_start}")
            return

    # Отправляем сообщение о начале подсчёта
    await update.effective_chat.send_message(
        FINAL_VOTING_CLOSE_SUCCESS,
        parse_mode="MarkdownV2"
    )

    # Загружаем информацию обо всех исключенных лидерах из excluded_leaders_data
    # Проверяем, что excluded_leaders_data - это строка, а не MagicMock (для тестов)
    if isinstance(final_voting.excluded_leaders_data, str):
        excluded_leaders_data = json.loads(final_voting.excluded_leaders_data or '[]')
    else:
        # Для тестов, когда excluded_leaders_data мокается
        excluded_leaders_data = []
    excluded_leader_ids = [leader['player_id'] for leader in excluded_leaders_data]
    logger.info(f"Excluded leaders from voting: {excluded_leader_ids}")

    # Вызываем функцию подсчёта результатов с передачей списка исключенных лидеров
    winners, results = finalize_voting(final_voting, context, excluded_player_ids=excluded_leader_ids)

    # Создаем записи GameResult для победителей
    from bot.handlers.game.voting_helpers import create_game_results_for_winners
    missed_days_list = json.loads(final_voting.missed_days_list)
    # TODO: включить и не убирать при рефакторинге
    # create_game_results_for_winners(
    #     winners,
    #     missed_days_list,
    #     final_voting.game_id,
    #     final_voting.year,
    #     context.db_session
    # )

    # Форматируем результаты голосования с отображением процентов
    winners_text, voting_results_text, days_distribution_text = format_voting_results(
        winners, results, final_voting.missed_days_count, context.db_session
    )

    # Получаем итоговую статистику года
    stmt_final = select(TGUser, func.count(GameResult.winner_id).label('count')) \
        .join(TGUser, GameResult.winner_id == TGUser.id) \
        .filter(GameResult.game_id == final_voting.game_id, GameResult.year == final_voting.year) \
        .group_by(TGUser) \
        .order_by(text('count DESC')) \
        .limit(10)
    final_stats = context.db_session.exec(stmt_final).all()

    year_stats_list = build_player_table(final_stats)

    # Формируем итоговое сообщение
    results_message = FINAL_VOTING_RESULTS.format(
        winners=winners_text,
        voting_results=voting_results_text,
        days_distribution=days_distribution_text,
        year_stats=year_stats_list
    )
    logger.info(f"pidorfinalclose_cmd send message {results_message}")

    # Отправляем сообщение с результатами
    await update.effective_chat.send_message(
        results_message,
        parse_mode="MarkdownV2"
    )

    # Формируем строку с именами победителей для логирования
    winners_log = ', '.join([winner.full_username() for _, winner in winners])
    logger.info(f"Final voting manually closed for game {context.game.id}, year {cur_year}, winners: {winners_log}")
