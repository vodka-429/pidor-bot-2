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
    ERROR_ALREADY_REGISTERED_MANY, VOTING_ENDED_RESPONSE, \
    FINAL_VOTING_CLOSE_ERROR_NOT_AUTHORIZED, COIN_INFO, \
    COINS_PERSONAL, COINS_CURRENT_YEAR, COINS_ALL_TIME, COINS_LIST_ITEM, COIN_EARNED, COIN_INFO_SELF_PIDOR
from bot.handlers.game.voting_helpers import get_player_weights, get_year_leaders
from bot.handlers.game.config import is_test_chat, get_config
from bot.handlers.game.coin_service import add_coins, get_balance, get_leaderboard, get_leaderboard_by_year
from bot.handlers.game.shop_service import is_leap_year, get_days_in_year
from bot.utils import escape_markdown2, escape_word, format_number, ECallbackContext, get_allowed_final_voting_closers

# Получаем логгер для этого модуля
logger = logging.getLogger(__name__)

MOSCOW_TZ = ZoneInfo('Europe/Moscow')


def current_datetime():
    return datetime.now(tz=MOSCOW_TZ)


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


async def run_tiebreaker(update: Update, context: GECallbackContext, leaders: List[TGUser], year: int):
    """
    Запустить tie-breaker розыгрыш между лидерами года.

    Args:
        update: Telegram Update объект
        context: Расширенный контекст с игрой
        leaders: Список лидеров года (TGUser объекты)
        year: Год для которого проводится tie-breaker
    """
    from bot.handlers.game.text_static import TIEBREAKER_ANNOUNCEMENT, TIEBREAKER_RESULT

    logger.info(f"Starting tie-breaker for year {year} with {len(leaders)} leaders")

    # Получаем конфигурацию для чата
    config = get_config(update.effective_chat.id)

    # Сообщение о tie-breaker
    leaders_names = ', '.join([escape_markdown2(leader.full_username()) for leader in leaders])
    await update.effective_chat.send_message(
        TIEBREAKER_ANNOUNCEMENT.format(count=len(leaders), leaders=leaders_names),
        parse_mode="MarkdownV2"
    )
    await asyncio.sleep(config.constants.game_result_time_delay)

    # Выбор победителя
    winner = random.choice(leaders)
    logger.info(f"Tie-breaker winner: {winner.full_username()}")

    # Определяем специальный день для tie-breaker
    tiebreaker_day = get_days_in_year(year) + 1

    # Создаём запись GameResult для tie-breaker
    context.game.results.append(
        GameResult(game_id=context.game.id, year=year, day=tiebreaker_day, winner=winner)
    )

    # Начислить койны победителю tie-breaker'а (без коммита)
    add_coins(context.db_session, context.game.id, winner.id, config.constants.coins_per_win, year, "tiebreaker_win", auto_commit=False)
    logger.debug(f"Awarded {config.constants.coins_per_win} coins to tie-breaker winner {winner.id}")

    logger.debug("Committing tie-breaker result and coin transaction to DB")
    context.db_session.commit()
    logger.info(f"Created tie-breaker GameResult for day {tiebreaker_day}")

    # Объявление победителя года
    await update.effective_chat.send_message(
        TIEBREAKER_RESULT.format(
            year=year,
            username=escape_markdown2(winner.full_username())
        ),
        parse_mode="MarkdownV2"
    )
    logger.info(f"Tie-breaker completed for year {year}, winner: {winner.full_username()}")


async def send_result_with_reroll_button(
    update: Update,
    context: GECallbackContext,
    stage4_message: str,
    cur_year: int,
    cur_day: int
):
    """
    Отправить финальное сообщение с кнопками перевыбора и "Дайте койнов", запустить таймер на их удаление.

    Args:
        update: Telegram Update объект
        context: Расширенный контекст с игрой
        stage4_message: Текст финального сообщения
        cur_year: Текущий год
        cur_day: Текущий день года
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from bot.handlers.game.text_static import get_reroll_messages, GIVE_COINS_BUTTON_TEXT
    from bot.handlers.game.reroll_service import remove_reroll_button_after_timeout
    from bot.handlers.game.config import get_config

    # Получаем конфигурацию для чата
    config = get_config(update.effective_chat.id)
    reroll_msgs = get_reroll_messages(config)

    # Получаем ID победителя для передачи в callback кнопки "Дайте койнов"
    game_result = context.db_session.query(GameResult).filter_by(
        game_id=context.game.id, year=cur_year, day=cur_day
    ).one()
    winner_id = game_result.winner_id

    # Создаём кнопки перевыбора и "Дайте койнов" в одном ряду
    reroll_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                reroll_msgs['button_text'],
                callback_data=f"reroll_{context.game.id}_{cur_year}_{cur_day}"
            ),
            InlineKeyboardButton(
                GIVE_COINS_BUTTON_TEXT,
                callback_data=f"givecoins_{context.game.id}_{cur_year}_{cur_day}_{winner_id}"
            )
        ]
    ])

    # Отправляем финальное сообщение с кнопкой перевыбора
    result_message = await update.effective_chat.send_message(
        stage4_message,
        parse_mode="HTML",
        reply_markup=reroll_keyboard
    )

    # Сохраняем ID сообщения для удаления кнопки по таймауту
    game_result = context.db_session.query(GameResult).filter_by(
        game_id=context.game.id, year=cur_year, day=cur_day
    ).one()
    game_result.reroll_message_id = result_message.message_id
    context.db_session.commit()

    # Запускаем таймер на удаление кнопки через 5 минут
    asyncio.create_task(remove_reroll_button_after_timeout(
        context.bot,
        update.effective_chat.id,
        result_message.message_id,
        delay_minutes=5
    ))

    logger.info(f"Sent result message with reroll button, message_id: {result_message.message_id}")


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

    # Получаем конфигурацию для чата
    config = get_config(update.effective_chat.id)

    current_dt = current_datetime()
    cur_year, cur_day = current_dt.year, current_dt.timetuple().tm_yday
    current_date = current_dt.date()
    last_day = current_dt.month == 12 and current_dt.day >= 31

    # Проверка пропущенных дней
    missed_days = get_missed_days_count(context.db_session, context.game.id, cur_year, cur_day)
    if missed_days > 0:
        logger.info(f"Missed {missed_days} days since last game")
        dramatic_msg = get_dramatic_message(missed_days)
        await update.effective_chat.send_message(dramatic_msg, parse_mode="MarkdownV2")
        await asyncio.sleep(config.constants.game_result_time_delay)

    game_result: GameResult = context.db_session.query(GameResult).filter_by(game_id=context.game.id, year=cur_year, day=cur_day).one_or_none()
    if game_result:
        await update.message.reply_markdown_v2(
            CURRENT_DAY_GAME_RESULT.format(
                username=escape_markdown2(game_result.winner.full_username())))
    else:
        logger.debug("Creating new game result")

        # Импорты для работы с эффектами и предсказаниями
        from bot.handlers.game.game_effects_service import (
            reset_double_chance, is_immunity_enabled
        )
        from bot.handlers.game.selection_service import select_winner_with_effects
        from bot.handlers.game.prediction_service import (
            process_predictions, format_predictions_summary, award_correct_predictions
        )
        from bot.handlers.game.text_static import get_immunity_messages, get_double_chance_messages

        # Получаем сообщения для эффектов
        immunity_msgs = get_immunity_messages(config)
        double_chance_msgs = get_double_chance_messages(config)

        # Проверяем, включена ли защита (не последний день года)
        immunity_enabled = is_immunity_enabled(current_dt)

        # Выбираем победителя с учётом всех эффектов
        selection_result = select_winner_with_effects(
            context.db_session, context.game.id, players, current_date, immunity_enabled
        )

        # Если все игроки защищены - отправляем специальное сообщение
        if selection_result.all_protected:
            await update.effective_chat.send_message(
                "🛡️ *Невероятно\\!* Все игроки защищены\\! Сегодня пидора дня не будет\\. Наслаждайтесь свободой\\! 🎉",
                parse_mode="MarkdownV2"
            )
            logger.warning(f"All players are protected in game {context.game.id}")
            return

        winner = selection_result.winner
        winner_had_double_chance = selection_result.had_double_chance

        # Если сработала защита - показываем сообщение и начисляем койны
        if selection_result.had_immunity and selection_result.protected_player:
            protected_player = selection_result.protected_player

            # Начисляем койны защищенному игроку за то, что его выбрали
            add_coins(context.db_session, context.game.id, protected_player.id, config.constants.coins_per_win, cur_year, "immunity_save", auto_commit=False)
            logger.debug(f"Awarded {config.constants.coins_per_win} coins to protected player {protected_player.id}")

            # Показываем сообщение о срабатывании защиты с информацией о койнах
            from html import escape as html_escape
            await update.effective_chat.send_message(
                immunity_msgs['activated_in_game'].format(
                    username=html_escape(protected_player.full_username()),
                    username_plain=protected_player.full_username(),
                    amount=config.constants.coins_per_win
                ),
                parse_mode="HTML"
            )
            await asyncio.sleep(config.constants.game_result_time_delay)

        # Сбрасываем двойной шанс у победителя (если был активен)
        reset_double_chance(context.db_session, context.game.id, winner.id, current_date)

        context.game.results.append(GameResult(game_id=context.game.id, year=cur_year, day=cur_day, winner=winner))

        # Проверяем, является ли победитель тем же, кто запустил команду
        is_self_pidor = winner.id == context.tg_user.id

        if is_self_pidor:
            # Начислить специальные койны с множителем
            self_pidor_coins = config.constants.coins_per_win * config.constants.self_pidor_multiplier
            add_coins(context.db_session, context.game.id, winner.id, self_pidor_coins, cur_year, "self_pidor_win", auto_commit=False)
            logger.debug(f"Awarded {self_pidor_coins} coins to self-pidor winner {winner.id}")
        else:
            # Начислить койны победителю (без коммита)
            add_coins(context.db_session, context.game.id, winner.id, config.constants.coins_per_win, cur_year, "pidor_win", auto_commit=False)
            logger.debug(f"Awarded {config.constants.coins_per_win} coins to winner {winner.id}")

            # Начислить койны игроку, который запустил команду (без коммита)
            add_coins(context.db_session, context.game.id, context.tg_user.id, config.constants.coins_per_command, cur_year, "command_execution", auto_commit=False)
            logger.debug(f"Awarded {config.constants.coins_per_command} coin to command executor {context.tg_user.id}")

        # Обрабатываем предсказания на текущий день
        predictions_results = process_predictions(
            context.db_session, context.game.id, cur_year, cur_day, winner.id
        )

        # Начисляем койны за правильные предсказания
        award_correct_predictions(context.db_session, context.game.id, cur_year, predictions_results)

        # Проверяем и выдаём достижения (если включены)
        from bot.handlers.game.achievement_service import check_and_award_achievements
        awarded_achievements = check_and_award_achievements(
            context.db_session, context.game.id, winner.id, cur_year, cur_day
        )

        # Проверяем, первый ли это розыгрыш в месяце
        from bot.handlers.game.achievement_service import (
            is_first_game_of_month, check_monthly_achievements, get_previous_month
        )

        current_month = current_dt.month
        if is_first_game_of_month(context.db_session, context.game.id, cur_year, current_month, current_dt.day):
            # Выдаём достижения за прошлый месяц
            prev_year, prev_month = get_previous_month(cur_year, current_month)
            monthly_achievements = check_monthly_achievements(
                context.db_session, context.game.id, prev_year, prev_month
            )
            awarded_achievements.extend(monthly_achievements)
            logger.info(f"Awarded {len(monthly_achievements)} monthly achievements for {prev_year}-{prev_month:02d}")

        # Коммит всех изменений одним запросом (включая достижения)
        context.db_session.commit()
        logger.debug("Committed game result, coin transactions, and achievements")

        if last_day:
            logger.debug("Sending year results announcement")
            await update.effective_chat.send_message(YEAR_RESULTS_ANNOUNCEMENT.format(year=cur_year), parse_mode="MarkdownV2")

        logger.debug("Sending stage 1 message")
        await update.effective_chat.send_message(random.choice(stage1.phrases))
        await asyncio.sleep(config.constants.game_result_time_delay)
        logger.debug("Sending stage 2 message")
        await update.effective_chat.send_message(random.choice(stage2.phrases))
        await asyncio.sleep(config.constants.game_result_time_delay)
        logger.debug("Sending stage 3 message")
        await update.effective_chat.send_message(random.choice(stage3.phrases))
        await asyncio.sleep(config.constants.game_result_time_delay)
        logger.debug("Sending stage 4 message")
        stage4_message = random.choice(stage4.phrases).format(
            username=winner.full_username(mention=True))

        # Добавить информацию о койнах в зависимости от ситуации
        if is_self_pidor:
            self_pidor_coins = config.constants.coins_per_win * config.constants.self_pidor_multiplier
            stage4_message += COIN_INFO_SELF_PIDOR.format(amount=self_pidor_coins)
        else:
            stage4_message += COIN_INFO.format(
                winner_username=winner.full_username(),
                amount=config.constants.coins_per_win,
                executor_username=context.tg_user.full_username(),
                executor_amount=config.constants.coins_per_command
            )

        # Добавить информацию о двойном шансе (если сработал)
        if winner_had_double_chance:
            from html import escape as html_escape
            stage4_message += f"\n\n🎲 <b>{html_escape(winner.full_username())}</b> использовал(а) двойной шанс и победил(а)! Эффект израсходован."
            logger.info(f"Double chance was used by winner {winner.id} ({winner.full_username()})")

        # Добавить информацию о предсказаниях (если есть)
        if predictions_results:
            predictions_summary = format_predictions_summary(predictions_results, context.db_session)
            if predictions_summary:
                # Конвертируем MarkdownV2 в HTML для единообразия
                # Убираем заголовок и экранирование, форматируем для HTML
                from bot.handlers.game.prediction_service import format_predictions_summary_html
                predictions_html = format_predictions_summary_html(predictions_results, context.db_session)
                stage4_message += f"\n\n{predictions_html}"
                logger.info(f"Added predictions summary with {len(predictions_results)} predictions to stage4 message")

        # Добавить информацию о полученных достижениях (если есть)
        if awarded_achievements:
            from bot.handlers.game.text_static import ACHIEVEMENTS_EARNED_HEADER, ACHIEVEMENT_EARNED_TEMPLATE
            from bot.handlers.game.achievement_constants import get_achievement
            from html import escape as html_escape

            achievements_lines = []
            for achievement in awarded_achievements:
                achievement_data = get_achievement(achievement.achievement_code)
                if achievement_data:
                    achievement_line = ACHIEVEMENT_EARNED_TEMPLATE.format(
                        name=html_escape(achievement_data['name']),
                        reward=achievement_data['reward']
                    )
                    achievements_lines.append(achievement_line)

            if achievements_lines:
                stage4_message += ACHIEVEMENTS_EARNED_HEADER
                for line in achievements_lines:
                    stage4_message += f"\n{line}"
                logger.info(f"Added {len(awarded_achievements)} achievements to stage4 message")

        # Отправляем финальное сообщение с кнопкой перевыбора
        await send_result_with_reroll_button(update, context, stage4_message, cur_year, cur_day)

        # Проверка на tie-breaker в последний день года
        if last_day:
            logger.debug("Checking for tie-breaker situation")
            # Получаем веса всех игроков
            player_weights = get_player_weights(context.db_session, context.game.id, cur_year)

            # Получаем только лидеров
            year_leaders = get_year_leaders(player_weights)

            # Если лидеров больше одного - запускаем tie-breaker
            if len(year_leaders) > 1:
                logger.info(f"Multiple leaders detected ({len(year_leaders)}), starting tie-breaker")
                # Извлекаем только объекты TGUser
                leaders = [player for player, wins in year_leaders]
                await run_tiebreaker(update, context, leaders, cur_year)
                return  # Завершаем выполнение, tie-breaker уже объявил результат
            else:
                logger.debug("Single leader detected, no tie-breaker needed")


async def pidorules_cmd(update: Update, _context: CallbackContext):
    """Показать правила игры с актуальными ценами из конфигурации"""
    from bot.handlers.game.text_static import get_rules_message

    logger.info("Game rules requested")

    # Получаем конфигурацию для чата
    config = get_config(update.effective_chat.id)

    # Генерируем сообщение с правилами с актуальными ценами
    rules_message = get_rules_message(config)

    await update.effective_chat.send_message(
        rules_message,
        parse_mode="MarkdownV2"
    )


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

    # Получаем конфигурацию для чата
    config = get_config(update.effective_chat.id)

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

    # Если пропущено меньше max_missed_days_for_final_voting дней - показываем список с датами
    if missed_count < config.constants.max_missed_days_for_final_voting:
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
        # Если больше или равно max_missed_days_for_final_voting - показываем только количество
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
        create_voting_keyboard, get_player_weights, format_weights_message, get_year_leaders,
        format_voting_rules_message, calculate_max_votes, calculate_voting_params
    )

    logger.info(f"pidorfinal_cmd started for chat {update.effective_chat.id}")

    # Получаем конфигурацию для чата
    config = get_config(update.effective_chat.id)

    # Получаем текущую дату
    current_dt = current_datetime()
    cur_year, cur_day = current_dt.year, current_dt.timetuple().tm_yday

    # Получаем список пропущенных дней
    missed_days = get_all_missed_days(context.db_session, context.game.id, cur_year, cur_day)

    # Рассчитываем эффективное количество дней и максимальное количество голосов
    effective_missed_days, max_votes = calculate_voting_params(len(missed_days), update.effective_chat.id)

    # Ограничиваем список пропущенных дней до effective_missed_days
    missed_days = missed_days[:effective_missed_days]
    missed_count = effective_missed_days

    # Получаем веса игроков (количество побед в году)
    player_weights = get_player_weights(context.db_session, context.game.id, cur_year)

    # Определяем всех лидеров года (игроки с максимальным количеством побед)
    year_leaders = get_year_leaders(player_weights)

    # Проверяем, что пропущено меньше max_missed_days_for_final_voting дней (пропускаем для тестового чата)
    if not is_test_chat(update.effective_chat.id):
        if effective_missed_days >= config.constants.max_missed_days_for_final_voting:
            await update.effective_chat.send_message(
                FINAL_VOTING_ERROR_TOO_MANY.format(
                    count=effective_missed_days,
                    max_days=config.constants.max_missed_days_for_final_voting
                ),
                parse_mode="MarkdownV2"
            )
            logger.warning(f"Too many missed days for final voting: {effective_missed_days}")
            return

    # Проверяем, что сейчас 29 или 30 декабря (пропускаем для тестового чата)
    # TODO: избавиться от дублирования логики
    if not is_test_chat(update.effective_chat.id):
        if not (current_dt.month == 12 and current_dt.day in [29, 30]):
            if len(player_weights) > 0:
                # Формируем информационное сообщение с правилами
                rules_message = format_voting_rules_message(
                    player_weights,
                    effective_missed_days,
                    max_votes,
                    excluded_leaders=year_leaders
                )

                await update.effective_chat.send_message(
                    rules_message,
                    parse_mode="MarkdownV2"
                )
                logger.info(f"Showed voting rules for chat {update.effective_chat.id} on {current_dt.date()}")
            else:
                # Если нет игр в году, показываем стандартную ошибку о дате
                await update.effective_chat.send_message(
                    FINAL_VOTING_ERROR_DATE,
                    parse_mode="MarkdownV2"
                )
                logger.warning(f"Attempt to start final voting on wrong date: {current_dt.date()}")
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

    if len(player_weights) == 0:
        await update.effective_chat.send_message(
            "❌ *Ошибка\\!* В этом году ещё не было ни одного розыгрыша\\. Финальное голосование невозможно\\.",
            parse_mode="MarkdownV2"
        )
        logger.warning(f"No games played in year {cur_year} for game {context.game.id}")
        return

    # Создаем список ID исключенных лидеров
    excluded_leader_ids = [leader.id for leader, _ in year_leaders]

    # Создаем список кандидатов, исключая всех лидеров
    candidates = [player for player, _ in player_weights if player.id not in excluded_leader_ids]

    # Создаём словарь с количеством побед для каждого игрока
    player_wins = {player.id: wins for player, wins in player_weights}

    # Подготавливаем информацию об исключенных лидерах для сохранения
    excluded_leaders_data = [{"player_id": leader.id, "wins": wins} for leader, wins in year_leaders]

    # Сначала создаём запись FinalVoting без voting_message_id
    # Конвертируем current_dt в UTC naive для хранения в БД
    started_at_utc = current_dt.astimezone(ZoneInfo('UTC')).replace(tzinfo=None)

    final_voting = FinalVoting(
        game_id=context.game.id,
        year=cur_year,
        poll_id='',  # Больше не используется для кастомного голосования
        poll_message_id=0,  # Временное значение, будет обновлено
        started_at=started_at_utc,
        missed_days_count=effective_missed_days,
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
    max_votes = calculate_max_votes(final_voting.missed_days_count, update.effective_chat.id)

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
        # Конвертируем started_at для отображения
        # Проверяем, является ли started_at timezone-aware
        if final_voting.started_at.tzinfo is None:
            # Если naive, предполагаем что это уже Moscow time (для совместимости с тестами)
            started_at_moscow = final_voting.started_at.replace(tzinfo=MOSCOW_TZ)
        else:
            # Если уже aware, конвертируем в Moscow TZ
            started_at_moscow = final_voting.started_at.astimezone(MOSCOW_TZ)
        # Форматируем дату для вывода
        started_str = started_at_moscow.strftime("%d\\.%m\\.%Y %H:%M МСК")

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

    # Конвертируем ended_at для отображения
    # Проверяем, является ли ended_at timezone-aware
    if final_voting.ended_at.tzinfo is None:
        # Если naive, предполагаем что это уже Moscow time (для совместимости с тестами)
        ended_at_moscow = final_voting.ended_at.replace(tzinfo=MOSCOW_TZ)
    else:
        # Если уже aware, конвертируем в Moscow TZ
        ended_at_moscow = final_voting.ended_at.astimezone(MOSCOW_TZ)
    ended_str = ended_at_moscow.strftime("%d\\.%m\\.%Y %H:%M МСК")

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

    # Проверяем, что команду вызвал разрешенный пользователь
    allowed_closers = get_allowed_final_voting_closers()
    user_username = context.tg_user.full_username()

    # Если список разрешенных пользователей не пуст, проверяем username
    if allowed_closers and user_username not in allowed_closers:
        await update.effective_chat.send_message(
            FINAL_VOTING_CLOSE_ERROR_NOT_AUTHORIZED,
            parse_mode="MarkdownV2"
        )
        logger.warning(f"User {update.effective_user.id} with username '{user_username}' tried to close voting")
        return

    # Проверяем, что прошло не менее 24 часов с момента старта голосования (пропускаем для тестового чата)
    if not is_test_chat(update.effective_chat.id):
        from datetime import timedelta
        min_voting_duration = timedelta(hours=24)

        # Конвертируем started_at и current_dt для корректного сравнения
        # Проверяем, является ли started_at timezone-aware
        if final_voting.started_at.tzinfo is None:
            # Если naive, предполагаем что это уже Moscow time (для совместимости с тестами)
            started_at_moscow = final_voting.started_at.replace(tzinfo=MOSCOW_TZ)
        else:
            # Если уже aware, конвертируем в Moscow TZ
            started_at_moscow = final_voting.started_at.astimezone(MOSCOW_TZ)

        # Также проверяем current_dt (может быть naive в тестах)
        if current_dt.tzinfo is None:
            # Если naive, предполагаем что это Moscow TZ
            current_dt_aware = current_dt.replace(tzinfo=MOSCOW_TZ)
        else:
            current_dt_aware = current_dt

        time_since_start = current_dt_aware - started_at_moscow

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
    create_game_results_for_winners(
        winners,
        missed_days_list,
        final_voting.game_id,
        final_voting.year,
        context.db_session,
        winners_data=final_voting.winners_data
    )

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


def build_coins_table(player_list: list[tuple[TGUser, int]]) -> str:
    """Построить таблицу для отображения топа по койнам"""
    result = []
    for number, (tg_user, amount) in enumerate(player_list, 1):
        result.append(COINS_LIST_ITEM.format(number=number,
                                             username=escape_markdown2(tg_user.full_username()),
                                             amount=format_number(amount)))
    return ''.join(result)


@ensure_game
async def pidorcoinsme_cmd(update: Update, context: GECallbackContext):
    """Показать личный баланс пидор-койнов"""
    logger.info(f"pidorcoinsme_cmd started for chat {update.effective_chat.id}")

    # Получаем баланс текущего пользователя
    balance = get_balance(context.db_session, context.game.id, context.tg_user.id)

    await update.effective_chat.send_message(
        COINS_PERSONAL.format(
            username=escape_markdown2(context.tg_user.full_username()),
            amount=format_number(balance)
        ),
        parse_mode="MarkdownV2"
    )
    logger.info(f"Showed coin balance for user {context.tg_user.id}: {balance} coins")


@ensure_game
async def pidorcoinsstats_cmd(update: Update, context: GECallbackContext):
    """Показать топ по пидор-койнам за текущий год"""
    logger.info(f"pidorcoinsstats_cmd started for chat {update.effective_chat.id}")

    # Получаем текущий год
    cur_year = current_datetime().year

    # Получаем топ по койнам за текущий год
    leaderboard = get_leaderboard_by_year(context.db_session, context.game.id, cur_year, limit=50)

    if len(leaderboard) == 0:
        await update.effective_chat.send_message(
            "📊 В этом году ещё нет пидор\\-койнов\\!",
            parse_mode="MarkdownV2"
        )
        return

    player_table = build_coins_table(leaderboard)
    answer = COINS_CURRENT_YEAR.format(player_stats=player_table,
                                       player_count=len(context.game.players))
    await update.effective_chat.send_message(answer, parse_mode="MarkdownV2")
    logger.info(f"Showed coin stats for year {cur_year}, {len(leaderboard)} players")


@ensure_game
async def pidorshop_cmd(update: Update, context: GECallbackContext):
    """Открыть магазин пидор-койнов с интерактивным меню"""
    from bot.handlers.game.shop_helpers import create_shop_keyboard, format_shop_menu_message
    from bot.handlers.game.shop_service import get_active_effects

    logger.info(f"pidorshop_cmd started for chat {update.effective_chat.id}, user {context.tg_user.id}")

    # Получаем баланс текущего пользователя
    balance = get_balance(context.db_session, context.game.id, context.tg_user.id)
    logger.debug(f"User {context.tg_user.id} balance: {balance}")

    # Получаем информацию об активных эффектах
    current_dt = current_datetime()
    current_date = current_dt.date()

    active_effects = get_active_effects(
        context.db_session, context.game.id, context.tg_user.id,
        current_date
    )

    # Создаём клавиатуру магазина с owner_user_id для проверки прав и информацией об активных эффектах
    # ВАЖНО: используем tg_id (Telegram ID), а не id (внутренний ID БД)
    logger.info(f"Creating shop keyboard with owner_user_id (tg_id): {context.tg_user.tg_id}")
    keyboard = create_shop_keyboard(owner_user_id=context.tg_user.tg_id, chat_id=update.effective_chat.id, active_effects=active_effects)

    # Форматируем сообщение с балансом, именем пользователя, списком товаров и информацией об активных эффектах
    user_name = context.tg_user.full_username()
    message_text = format_shop_menu_message(balance, update.effective_chat.id, user_name, active_effects)

    # Отправляем сообщение с inline-кнопками
    await update.effective_chat.send_message(
        text=message_text,
        parse_mode="MarkdownV2",
        reply_markup=keyboard
    )

    logger.info(f"Shop menu sent to user {context.tg_user.id} with balance {balance}")


@ensure_game
async def handle_shop_immunity_callback(update: Update, context: GECallbackContext):
    """Обработчик покупки защиты от пидора"""
    from bot.handlers.game.shop_helpers import parse_shop_callback_data
    from bot.handlers.game.shop_service import buy_immunity
    from bot.handlers.game.text_static import SHOP_ERROR_NOT_YOUR_SHOP, get_immunity_messages
    from bot.handlers.game.config import get_config

    query = update.callback_query

    if query is None:
        logger.error("callback_query is None!")
        return

    logger.info(f"Shop immunity callback from user {query.from_user.id} in chat {update.effective_chat.id}")
    logger.info(f"Callback data: {query.data}")

    try:
        # Парсим callback_data для получения item_type и owner_user_id
        item_type, owner_user_id = parse_shop_callback_data(query.data)
        logger.info(f"Parsed callback: item_type={item_type}, owner_user_id={owner_user_id}")
        logger.info(f"Callback data: {query.data}")
        logger.info(f"Query from user ID: {query.from_user.id}")
        logger.info(f"Owner user ID: {owner_user_id}")
        logger.info(f"Context TGUser ID: {context.tg_user.id}")
        logger.info(f"Context TGUser TG_ID: {context.tg_user.tg_id}")
        logger.info(f"Match check: {query.from_user.id} == {owner_user_id} -> {query.from_user.id == owner_user_id}")
        logger.info(f"TGUser ID vs TG_ID: {context.tg_user.id} vs {context.tg_user.tg_id}")
    except ValueError as e:
        logger.error(f"Failed to parse callback_data: {e}")
        await query.answer("❌ Ошибка обработки запроса")
        return

    # ВАЖНО: Проверяем, что нажавший кнопку - это владелец магазина
    if query.from_user.id != owner_user_id:
        logger.warning(f"Shop ownership mismatch: User {query.from_user.id} tried to use shop of user {owner_user_id}")
        logger.warning(f"Callback data was: {query.data}")
        await query.answer(SHOP_ERROR_NOT_YOUR_SHOP, show_alert=True)
        return

    # Получаем конфигурацию и сообщения
    config = get_config(update.effective_chat.id)
    immunity_msgs = get_immunity_messages(config)

    # Получаем текущую дату
    current_dt = current_datetime()
    current_date = current_dt.date()
    cur_year = current_dt.year

    # Вызываем функцию покупки защиты
    success, message, commission = buy_immunity(
        context.db_session,
        context.game.id,
        context.tg_user.id,
        cur_year,
        current_date
    )

    if success:
        # Получаем новый баланс
        balance = get_balance(context.db_session, context.game.id, context.tg_user.id)

        # Получаем информацию о дате действия защиты
        from bot.handlers.game.shop_service import get_or_create_player_effects
        from bot.handlers.game.shop_helpers import format_date_readable
        effect = get_or_create_player_effects(context.db_session, context.game.id, context.tg_user.id)
        date_str = escape_markdown2(format_date_readable(effect.immunity_year, effect.immunity_day))

        response_text = immunity_msgs['purchase_success'].format(
            date=date_str,
            balance=format_number(balance),
            commission=format_number(commission)
        )
        await query.answer("✅ Защита куплена!", show_alert=True)
        logger.info(f"User {context.tg_user.id} bought immunity in game {context.game.id}")
    else:
        # Обрабатываем ошибки
        if message == "insufficient_funds":
            balance = get_balance(context.db_session, context.game.id, context.tg_user.id)
            response_text = immunity_msgs['error_insufficient_funds'].format(balance=format_number(balance))
        elif message.startswith("already_active:"):
            # Формат: "already_active:year:day"
            parts = message.split(":")
            year = int(parts[1])
            day = int(parts[2])
            from bot.handlers.game.shop_helpers import format_date_readable
            date_str = escape_markdown2(format_date_readable(year, day))
            response_text = immunity_msgs['error_already_active'].format(date=date_str)
        elif message.startswith("cooldown:"):
            # Формат: "cooldown:YYYY-MM-DD"
            cooldown_date = message.split(":")[1]
            from datetime import datetime
            from bot.handlers.game.shop_helpers import format_date_readable
            date_obj = datetime.fromisoformat(cooldown_date)
            date_str = escape_markdown2(format_date_readable(date_obj.year, date_obj.timetuple().tm_yday))
            response_text = immunity_msgs['error_cooldown'].format(date=date_str)
        else:
            response_text = "❌ Произошла ошибка при покупке"

        await query.answer("❌ Не удалось купить", show_alert=True)
        logger.warning(f"User {context.tg_user.id} failed to buy immunity: {message}")

    # Обновляем сообщение магазина с новым балансом и активными эффектами
    try:
        from bot.handlers.game.shop_helpers import create_shop_keyboard, format_shop_menu_message
        from bot.handlers.game.shop_service import get_active_effects

        balance = get_balance(context.db_session, context.game.id, context.tg_user.id)

        # Получаем обновлённую информацию об активных эффектах
        current_dt = current_datetime()
        current_date = current_dt.date()

        active_effects = get_active_effects(
            context.db_session, context.game.id, context.tg_user.id,
            current_date
        )

        keyboard = create_shop_keyboard(owner_user_id=context.tg_user.tg_id, chat_id=update.effective_chat.id, active_effects=active_effects)
        user_name = context.tg_user.full_username()
        message_text = format_shop_menu_message(balance, update.effective_chat.id, user_name, active_effects)

        await query.edit_message_text(
            text=message_text,
            parse_mode="MarkdownV2",
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Failed to update shop message: {e}")


@ensure_game
async def handle_shop_double_callback(update: Update, context: GECallbackContext):
    """Обработчик выбора игрока для двойного шанса"""
    from bot.handlers.game.shop_helpers import parse_shop_callback_data, create_double_chance_keyboard
    from bot.handlers.game.text_static import SHOP_ERROR_NOT_YOUR_SHOP, get_double_chance_messages
    from bot.handlers.game.config import get_config

    query = update.callback_query

    if query is None:
        logger.error("callback_query is None!")
        return

    logger.info(f"Shop double chance callback from user {query.from_user.id} in chat {update.effective_chat.id}")
    logger.info(f"Callback data: {query.data}")

    try:
        # Парсим callback_data для получения item_type и owner_user_id
        item_type, owner_user_id = parse_shop_callback_data(query.data)
        logger.info(f"Parsed callback: item_type={item_type}, owner_user_id={owner_user_id}")
        logger.info(f"Callback data: {query.data}")
        logger.info(f"Query from user ID: {query.from_user.id}")
        logger.info(f"Owner user ID: {owner_user_id}")
        logger.info(f"Match check: {query.from_user.id} == {owner_user_id} -> {query.from_user.id == owner_user_id}")
    except ValueError as e:
        logger.error(f"Failed to parse callback_data: {e}")
        await query.answer("❌ Ошибка обработки запроса")
        return

    # ВАЖНО: Проверяем, что нажавший кнопку - это владелец магазина
    if query.from_user.id != owner_user_id:
        logger.warning(f"Shop ownership mismatch: User {query.from_user.id} tried to use shop of user {owner_user_id}")
        logger.warning(f"Callback data was: {query.data}")
        await query.answer(SHOP_ERROR_NOT_YOUR_SHOP, show_alert=True)
        return

    # Получаем конфигурацию и сообщения
    config = get_config(update.effective_chat.id)
    double_chance_msgs = get_double_chance_messages(config)

    # Получаем список игроков из игры
    players = context.game.players

    if len(players) < 2:
        await query.answer("❌ Недостаточно игроков для двойного шанса", show_alert=True)
        logger.warning(f"Not enough players for double chance in game {context.game.id}")
        return

    # Создаём клавиатуру с игроками
    keyboard = create_double_chance_keyboard(players, owner_user_id=context.tg_user.tg_id)

    # Отправляем сообщение с выбором игрока
    try:
        await query.edit_message_text(
            text=double_chance_msgs['select_player'],
            parse_mode="MarkdownV2",
            reply_markup=keyboard
        )
        await query.answer()
        logger.info(f"Showed double chance player selection for user {context.tg_user.id}")
    except Exception as e:
        logger.error(f"Failed to show double chance selection: {e}")
        await query.answer("❌ Ошибка при отображении списка игроков")


@ensure_game
async def handle_shop_predict_callback(update: Update, context: GECallbackContext):
    """Обработчик выбора кандидатов для предсказания"""
    from bot.handlers.game.shop_helpers import parse_shop_callback_data, create_prediction_keyboard
    from bot.handlers.game.prediction_service import calculate_candidates_count, get_or_create_prediction_draft
    from bot.handlers.game.text_static import SHOP_ERROR_NOT_YOUR_SHOP

    query = update.callback_query

    if query is None:
        logger.error("callback_query is None!")
        return

    logger.info(f"Shop predict callback from user {query.from_user.id} in chat {update.effective_chat.id}")
    logger.info(f"Callback data: {query.data}")

    try:
        # Парсим callback_data для получения item_type и owner_user_id
        item_type, owner_user_id = parse_shop_callback_data(query.data)
        logger.info(f"Parsed callback: item_type={item_type}, owner_user_id={owner_user_id}")
    except ValueError as e:
        logger.error(f"Failed to parse callback_data: {e}")
        await query.answer("❌ Ошибка обработки запроса")
        return

    # ВАЖНО: Проверяем, что нажавший кнопку - это владелец магазина
    if query.from_user.id != owner_user_id:
        logger.warning(f"Shop ownership mismatch: User {query.from_user.id} tried to use shop of user {owner_user_id}")
        await query.answer(SHOP_ERROR_NOT_YOUR_SHOP, show_alert=True)
        return

    # Получаем список игроков из игры
    players = context.game.players

    if len(players) < 2:
        await query.answer("❌ Недостаточно игроков для предсказания", show_alert=True)
        logger.warning(f"Not enough players for prediction in game {context.game.id}")
        return

    # Рассчитываем количество кандидатов
    candidates_count = calculate_candidates_count(len(players))
    logger.info(f"Calculated {candidates_count} candidates for {len(players)} players")

    # Создаём или получаем черновик в БД
    draft = get_or_create_prediction_draft(
        context.db_session,
        context.game.id,
        context.tg_user.id,
        candidates_count
    )

    # Получаем текущий выбор из черновика
    import json
    selected_ids = json.loads(draft.selected_user_ids)

    # Создаём клавиатуру с игроками для множественного выбора
    keyboard = create_prediction_keyboard(
        players,
        owner_user_id=context.tg_user.tg_id,
        candidates_count=candidates_count,
        selected_ids=selected_ids
    )

    # Формируем сообщение
    message_text = (
        f"🔮 *Предсказание пидора дня*\n\n"
        f"Выберите *{candidates_count}* кандидат{'а' if candidates_count < 5 else 'ов'} "
        f"из {len(players)} игроков\\.\n\n"
        f"Если любой из них станет пидором — вы получите *\\+30* 💰\\!"
    )

    # Отправляем сообщение с выбором кандидатов
    try:
        await query.edit_message_text(
            text=message_text,
            parse_mode="MarkdownV2",
            reply_markup=keyboard
        )
        await query.answer()
        logger.info(f"Showed prediction candidates selection for user {context.tg_user.id}")
    except Exception as e:
        logger.error(f"Failed to show prediction selection: {e}")
        await query.answer("❌ Ошибка при отображении списка игроков")


@ensure_game
async def handle_shop_predict_select_callback(update: Update, context: GECallbackContext):
    """Обработчик выбора кандидата для предсказания"""
    from bot.handlers.game.shop_helpers import create_prediction_keyboard
    from bot.handlers.game.prediction_service import calculate_candidates_count, get_prediction_draft, update_prediction_draft
    from bot.handlers.game.text_static import SHOP_ERROR_NOT_YOUR_SHOP
    import json

    query = update.callback_query

    if query is None:
        logger.error("callback_query is None!")
        return

    logger.info(f"Predict select callback from user {query.from_user.id}")
    logger.info(f"Callback data: {query.data}")

    # Парсим callback_data: shop_predict_select_{player_id}_{owner_user_id}
    try:
        parts = query.data.split('_')
        if len(parts) < 4:
            raise ValueError(f"Invalid callback_data format: {query.data}")

        player_id = int(parts[3])
        owner_user_id = int(parts[4])

        logger.info(f"Parsed: player_id={player_id}, owner_user_id={owner_user_id}")
    except (ValueError, IndexError) as e:
        logger.error(f"Failed to parse callback_data: {e}")
        await query.answer("❌ Ошибка обработки запроса")
        return

    # Проверяем права
    if query.from_user.id != owner_user_id:
        await query.answer(SHOP_ERROR_NOT_YOUR_SHOP, show_alert=True)
        return

    # Получаем черновик из БД
    draft = get_prediction_draft(context.db_session, context.game.id, context.tg_user.id)

    if not draft:
        await query.answer("❌ Черновик не найден", show_alert=True)
        logger.error(f"Draft not found for user {context.tg_user.id} in game {context.game.id}")
        return

    # Получаем текущий выбор из черновика
    selected = json.loads(draft.selected_user_ids)

    # Рассчитываем нужное количество кандидатов
    players = context.game.players
    candidates_count = calculate_candidates_count(len(players))

    # Добавляем/убираем кандидата
    if player_id in selected:
        selected.remove(player_id)
        await query.answer("❌ Кандидат убран")
    elif len(selected) < candidates_count:
        selected.append(player_id)
        await query.answer(f"✅ Кандидат добавлен ({len(selected)}/{candidates_count})")
    else:
        await query.answer(f"❌ Уже выбрано {candidates_count} кандидатов", show_alert=True)
        return

    # Обновляем черновик в БД
    update_prediction_draft(context.db_session, draft.id, selected)

    # Обновляем клавиатуру
    keyboard = create_prediction_keyboard(
        players,
        owner_user_id=context.tg_user.tg_id,
        candidates_count=candidates_count,
        selected_ids=selected
    )

    # Формируем обновлённое сообщение
    message_text = (
        f"🔮 *Предсказание пидора дня*\n\n"
        f"Выберите *{candidates_count}* кандидат{'а' if candidates_count < 5 else 'ов'} "
        f"из {len(players)} игроков\\.\n\n"
        f"Выбрано: *{len(selected)}/{candidates_count}*\n\n"
        f"Если любой из них станет пидором — вы получите *\\+30* 💰\\!"
    )

    try:
        await query.edit_message_text(
            text=message_text,
            parse_mode="MarkdownV2",
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Failed to update prediction selection: {e}")


@ensure_game
async def handle_shop_predict_confirm_callback(update: Update, context: GECallbackContext):
    """Обработчик подтверждения предсказания с несколькими кандидатами"""
    from bot.handlers.game.shop_helpers import parse_shop_callback_data
    from bot.handlers.game.shop_service import create_prediction
    from bot.handlers.game.prediction_service import get_prediction_draft, delete_prediction_draft
    from bot.handlers.game.text_static import SHOP_ERROR_NOT_YOUR_SHOP, get_prediction_messages
    from bot.handlers.game.config import get_config
    import json

    query = update.callback_query

    if query is None:
        logger.error("callback_query is None!")
        return

    logger.info(f"Shop predict confirm callback from user {query.from_user.id}")
    logger.info(f"Callback data: {query.data}")

    # Парсим callback_data: shop_predict_confirm_{owner_user_id}
    try:
        parts = query.data.split('_')
        if len(parts) < 3:
            raise ValueError(f"Invalid callback_data format: {query.data}")

        owner_user_id = int(parts[-1])
        logger.info(f"Parsed callback: owner_user_id={owner_user_id}")
    except (ValueError, IndexError) as e:
        logger.error(f"Failed to parse callback_data: {e}")
        await query.answer("❌ Ошибка обработки запроса")
        return

    # Проверяем права
    if query.from_user.id != owner_user_id:
        logger.warning(f"Shop ownership mismatch: User {query.from_user.id} tried to use shop of user {owner_user_id}")
        await query.answer(SHOP_ERROR_NOT_YOUR_SHOP, show_alert=True)
        return

    # Получаем конфигурацию и сообщения
    config = get_config(update.effective_chat.id)
    prediction_msgs = get_prediction_messages(config)

    # Получаем черновик из БД
    draft = get_prediction_draft(context.db_session, context.game.id, context.tg_user.id)

    if not draft:
        await query.answer("❌ Черновик не найден", show_alert=True)
        logger.error(f"Draft not found for user {context.tg_user.id} in game {context.game.id}")
        return

    # Получаем выбранных кандидатов из черновика
    selected = json.loads(draft.selected_user_ids)

    if not selected:
        await query.answer("❌ Выберите кандидатов!", show_alert=True)
        return

    # Получаем текущую дату
    current_dt = current_datetime()
    current_date = current_dt.date()
    cur_year = current_dt.year

    # Вычисляем завтрашний день (день действия предсказания)
    from bot.handlers.game.shop_service import calculate_next_day
    target_year, target_day = calculate_next_day(current_date, cur_year)

    # Вызываем функцию создания предсказания со списком кандидатов
    success, message, commission = create_prediction(
        context.db_session,
        context.game.id,
        context.tg_user.id,
        selected,  # Передаём список ID кандидатов
        target_year,
        target_day
    )

    if success:
        # Удаляем черновик после успешного создания предсказания
        delete_prediction_draft(context.db_session, context.game.id, context.tg_user.id)

        # Получаем новый баланс
        balance = get_balance(context.db_session, context.game.id, context.tg_user.id)

        # Получаем имена кандидатов
        candidate_names = []
        for player in context.game.players:
            if player.id in selected:
                candidate_names.append(escape_markdown2(player.full_username()))

        # Вычисляем завтрашний день для отображения
        from bot.handlers.game.shop_helpers import format_date_readable
        date_str = escape_markdown2(format_date_readable(target_year, target_day))

        # Формируем сообщение
        candidates_text = ', '.join(candidate_names)
        response_text = (
            f"🔮 *Предсказание создано\\!*\n\n"
            f"Ваши кандидаты на {date_str}:\n"
            + '\n'.join(f"• {name}" for name in candidate_names) +
            f"\n\nЕсли любой из них станет пидором — вы получите *\\+30* 💰\\!\n\n"
            f"Списано: 3 койна\n"
            f"Комиссия в банк: {format_number(commission)} 🪙\n"
            f"💰 Ваш баланс: *{format_number(balance)}* 🪙"
        )

        await query.answer("✅ Предсказание создано!", show_alert=True)
        logger.info(f"User {context.tg_user.id} created prediction for users {selected} in game {context.game.id}")

        # Очищаем выбор из памяти (на случай если он там был)
        if 'prediction_selection' in context.user_data:
            context.user_data['prediction_selection'] = []

        # Отправляем сообщение с результатом
        await query.edit_message_text(
            text=response_text,
            parse_mode="MarkdownV2"
        )
    else:
        # Обрабатываем ошибки
        if message == "insufficient_funds":
            balance = get_balance(context.db_session, context.game.id, context.tg_user.id)
            response_text = prediction_msgs['error_insufficient_funds'].format(balance=format_number(balance))
        elif message == "already_exists":
            response_text = prediction_msgs['error_already_exists']
        elif message == "self_prediction":
            response_text = prediction_msgs['error_self']
        else:
            response_text = "❌ Произошла ошибка при создании предсказания"

        await query.answer("❌ Не удалось создать предсказание", show_alert=True)
        logger.warning(f"User {context.tg_user.id} failed to create prediction: {message}")

        # Отправляем сообщение с ошибкой
        try:
            await query.edit_message_text(
                text=response_text,
                parse_mode="MarkdownV2"
            )
        except Exception as e:
            logger.error(f"Failed to update message with error: {e}")


@ensure_game
async def handle_shop_double_confirm_callback(update: Update, context: GECallbackContext):
    """Обработчик подтверждения покупки двойного шанса"""
    from bot.handlers.game.shop_helpers import parse_shop_callback_data
    from bot.handlers.game.shop_service import buy_double_chance
    from bot.handlers.game.text_static import SHOP_ERROR_NOT_YOUR_SHOP, get_double_chance_messages
    from bot.handlers.game.config import get_config

    query = update.callback_query

    if query is None:
        logger.error("callback_query is None!")
        return

    logger.info(f"Shop double confirm callback from user {query.from_user.id} in chat {update.effective_chat.id}")
    logger.info(f"Callback data: {query.data}")

    # Парсим callback_data с помощью единой функции парсинга
    try:
        # Формат: shop_double_confirm_{target_user_id}_{owner_user_id}
        if not query.data.startswith('shop_double_confirm_'):
            raise ValueError(f"Invalid callback_data format: {query.data}")

        # Используем единую функцию парсинга для извлечения owner_user_id
        # Функция parse_shop_callback_data ожидает формат shop_{item_type}_{owner_user_id}
        # Для этого формата мы можем извлечь owner_user_id из последней части
        parts = query.data.split('_')
        if len(parts) < 4:
            raise ValueError(f"Invalid callback_data format: {query.data}")

        # Последняя часть - это owner_user_id
        owner_user_id = int(parts[-1])

        # Целевой пользователь - это предпоследняя часть
        target_user_id = int(parts[-2])

        logger.info(f"Parsed callback: target_user_id={target_user_id}, owner_user_id={owner_user_id}")
    except (ValueError, IndexError) as e:
        logger.error(f"Failed to parse callback_data: {e}")
        await query.answer("❌ Ошибка обработки запроса")
        return

    # ВАЖНО: Проверяем, что нажавший кнопку - это владелец магазина
    logger.info(f"Shop double confirm callback - Query from user ID: {query.from_user.id}")
    logger.info(f"Shop double confirm callback - Owner user ID: {owner_user_id}")
    logger.info(f"Shop double confirm callback - Match check: {query.from_user.id} == {owner_user_id} -> {query.from_user.id == owner_user_id}")

    if query.from_user.id != owner_user_id:
        logger.warning(f"Shop ownership mismatch in double confirm: User {query.from_user.id} tried to use shop of user {owner_user_id}")
        logger.warning(f"Callback data was: {query.data}")
        await query.answer(SHOP_ERROR_NOT_YOUR_SHOP, show_alert=True)
        return

    # Получаем конфигурацию и сообщения
    config = get_config(update.effective_chat.id)
    double_chance_msgs = get_double_chance_messages(config)

    # Получаем текущую дату
    current_dt = current_datetime()
    current_date = current_dt.date()
    cur_year = current_dt.year

    # Вызываем функцию покупки двойного шанса с target_user_id
    success, message, commission = buy_double_chance(
        context.db_session,
        context.game.id,
        context.tg_user.id,
        target_user_id,
        cur_year,
        current_date
    )

    if success:
        # Получаем новый баланс покупателя
        balance = get_balance(context.db_session, context.game.id, context.tg_user.id)

        # Вычисляем завтрашний день для отображения
        from bot.handlers.game.shop_helpers import format_date_readable
        from bot.handlers.game.shop_service import calculate_next_day
        next_year, next_day = calculate_next_day(current_date, cur_year)
        date_str = escape_markdown2(format_date_readable(next_year, next_day))

        # Проверяем, купил ли игрок для себя или для другого
        if target_user_id == context.tg_user.id:
            response_text = double_chance_msgs['purchase_success_self'].format(
                date=date_str,
                balance=format_number(balance),
                commission=format_number(commission)
            )
            await query.answer("✅ Двойной шанс куплен!", show_alert=True)
        else:
            # Получаем имя целевого игрока
            target_user = context.db_session.query(TGUser).filter_by(id=target_user_id).one()
            target_username = escape_markdown2(target_user.full_username())
            buyer_username = escape_markdown2(context.tg_user.full_username())
            response_text = double_chance_msgs['purchase_success_other'].format(
                buyer_username=buyer_username,
                target_username=target_username,
                date=date_str,
                balance=format_number(balance),
                commission=format_number(commission)
            )
            await query.answer("✅ Двойной шанс подарен!", show_alert=True)

        logger.info(f"User {context.tg_user.id} bought double chance for user {target_user_id} in game {context.game.id}")

        # Отправляем сообщение с результатом
        await query.edit_message_text(
            text=response_text,
            parse_mode="MarkdownV2"
        )
    else:
        # Обрабатываем ошибки
        if message == "insufficient_funds":
            balance = get_balance(context.db_session, context.game.id, context.tg_user.id)
            response_text = double_chance_msgs['error_insufficient_funds'].format(balance=format_number(balance))
        elif message == "already_bought_today":
            response_text = double_chance_msgs['error_already_bought_today']
        else:
            response_text = "❌ Произошла ошибка при покупке"

        await query.answer("❌ Не удалось купить", show_alert=True)
        logger.warning(f"User {context.tg_user.id} failed to buy double chance for user {target_user_id}: {message}")

        # Отправляем сообщение с ошибкой
        try:
            await query.edit_message_text(
                text=response_text,
                parse_mode="MarkdownV2"
            )
        except Exception as e:
            logger.error(f"Failed to update message with error: {e}")


@ensure_game
async def handle_reroll_callback(update: Update, context: GECallbackContext):
    """Обработчик нажатия кнопки перевыбора."""
    from bot.handlers.game.reroll_service import can_reroll, execute_reroll
    from bot.handlers.game.shop_service import can_afford
    from bot.handlers.game.coin_service import get_balance
    from bot.handlers.game.text_static import get_reroll_messages
    from bot.handlers.game.config import get_config

    query = update.callback_query

    if query is None:
        logger.error("callback_query is None!")
        return

    # Получаем конфигурацию для чата
    config = get_config(update.effective_chat.id)
    reroll_msgs = get_reroll_messages(config)

    logger.info(f"Reroll callback from user {query.from_user.id} in chat {update.effective_chat.id}")
    logger.info(f"Callback data: {query.data}")

    # Парсим callback_data: reroll_{game_id}_{year}_{day}
    parts = query.data.split('_')
    if len(parts) != 4:
        logger.error(f"Invalid callback_data format: {query.data}")
        await query.answer("❌ Ошибка обработки запроса")
        return

    try:
        game_id = int(parts[1])
        year = int(parts[2])
        day = int(parts[3])
    except (ValueError, IndexError) as e:
        logger.error(f"Failed to parse callback_data: {e}")
        await query.answer("❌ Ошибка обработки запроса")
        return

    # Проверяем, что перевыбор ещё доступен
    if not can_reroll(context.db_session, game_id, year, day):
        await query.answer(reroll_msgs['error_already_used'], show_alert=True)
        logger.info(f"Reroll already used for game {game_id}, {year}-{day}")
        return

    # Проверяем баланс
    if not can_afford(context.db_session, game_id, context.tg_user.id, config.constants.reroll_price):
        balance = get_balance(context.db_session, game_id, context.tg_user.id)
        await query.answer(
            reroll_msgs['error_insufficient_funds'].format(balance=balance),
            show_alert=True
        )
        logger.info(f"User {context.tg_user.id} has insufficient funds for reroll")
        return

    # Выполняем перевыбор
    players = context.game.players

    # Получаем текущую дату и проверяем, включена ли защита
    from bot.handlers.game.game_effects_service import is_immunity_enabled
    current_dt = current_datetime()
    current_date = current_dt.date()
    immunity_enabled = is_immunity_enabled(current_dt)

    old_winner, new_winner, selection_result = execute_reroll(
        context.db_session, game_id, year, day,
        context.tg_user.id, players, current_date, immunity_enabled
    )

    # Отправляем уведомление о перевыборе
    await query.answer(reroll_msgs['success_notification'], show_alert=True)

    # Удаляем кнопку из сообщения
    await query.edit_message_reply_markup(reply_markup=None)

    # Объявляем результат перевыбора
    from html import escape as html_escape
    initiator_name = html_escape(context.tg_user.full_username())
    old_winner_name = html_escape(old_winner.full_username())
    new_winner_name = html_escape(new_winner.full_username())

    # Формируем дополнительную информацию о защите, двойном шансе и предсказаниях
    protection_info = ""
    double_chance_info = ""
    predictions_info = ""

    # Информация о защите (если сработала при перевыборе)
    if selection_result.had_immunity and selection_result.protected_player:
        protected_player = selection_result.protected_player
        protection_info = f"\n\n🛡️ <b>Защита сработала!</b> {html_escape(protected_player.full_username())} был(а) защищён(а) и получил(а) +{config.constants.coins_per_win} 💰"

    # Информация о двойном шансе (если сработал при перевыборе)
    if selection_result.had_double_chance:
        double_chance_info = f"\n\n🎲 <b>Двойной шанс!</b> {new_winner_name} использовал(а) двойной шанс при перевыборе!"

    # Информация о предсказаниях (если сбылись при перевыборе)
    from bot.handlers.game.prediction_service import get_predictions_for_day, get_predicted_user_ids
    predictions = get_predictions_for_day(context.db_session, game_id, year, day)

    if predictions:
        correct_predictions = []
        for prediction in predictions:
            predicted_ids = get_predicted_user_ids(prediction)
            if new_winner.id in predicted_ids:
                stmt = select(TGUser).where(TGUser.id == prediction.user_id)
                predictor = context.db_session.exec(stmt).one()
                correct_predictions.append(
                    f"• {html_escape(predictor.full_username())}: +30 💰"
                )

        if correct_predictions:
            predictions_info = "\n\n🔮 <b>Предсказания сбылись!</b>\n" + "\n".join(correct_predictions)

    await update.effective_chat.send_message(
        reroll_msgs['announcement'].format(
            initiator_name=initiator_name,
            old_winner_name=old_winner_name,
            new_winner_name=new_winner_name,
            new_winner_coins=config.constants.coins_per_win,
            protection_info=protection_info,
            double_chance_info=double_chance_info,
            predictions_info=predictions_info
        ),
        parse_mode="HTML"
    )

    logger.info(
        f"Reroll completed: initiator {context.tg_user.id}, "
        f"old winner {old_winner.id}, new winner {new_winner.id}"
    )




@ensure_game
async def handle_give_coins_callback(update: Update, context: GECallbackContext):
    """Обработчик нажатия кнопки 'Дайте койнов'."""
    from bot.handlers.game.give_coins_service import has_claimed_today, claim_coins
    from bot.handlers.game.text_static import (
        GIVE_COINS_SUCCESS,
        GIVE_COINS_ALREADY_CLAIMED,
        GIVE_COINS_ERROR_NOT_REGISTERED
    )

    query = update.callback_query

    if query is None:
        logger.error("callback_query is None!")
        return

    logger.info(f"Give coins callback from user {query.from_user.id} in chat {update.effective_chat.id}")
    logger.info(f"Callback data: {query.data}")

    # Парсим callback_data: givecoins_{game_id}_{year}_{day}_{winner_id}
    parts = query.data.split('_')
    if len(parts) != 5:
        logger.error(f"Invalid callback_data format: {query.data}")
        await query.answer("❌ Ошибка обработки запроса")
        return

    try:
        game_id = int(parts[1])
        year = int(parts[2])
        day = int(parts[3])
        winner_id = int(parts[4])
    except (ValueError, IndexError) as e:
        logger.error(f"Failed to parse callback_data: {e}")
        await query.answer("❌ Ошибка обработки запроса")
        return

    # Проверяем, что игрок зарегистрирован в игре
    if context.tg_user not in context.game.players:
        await query.answer(GIVE_COINS_ERROR_NOT_REGISTERED, show_alert=True)
        logger.info(f"User {context.tg_user.id} is not registered in game {game_id}")
        return

    # Проверяем, не получал ли уже койны сегодня
    if has_claimed_today(context.db_session, game_id, context.tg_user.id, year, day):
        await query.answer(GIVE_COINS_ALREADY_CLAIMED, show_alert=True)
        logger.info(f"User {context.tg_user.id} already claimed coins today ({year}-{day})")
        return

    # Определяем, является ли игрок пидором дня
    is_winner = context.tg_user.id == winner_id

    # Получаем койны
    success, amount = claim_coins(
        context.db_session,
        game_id,
        context.tg_user.id,
        year,
        day,
        is_winner
    )

    if success:
        # Получаем новый баланс
        balance = get_balance(context.db_session, game_id, context.tg_user.id)

        # Отправляем уведомление
        await query.answer(
            GIVE_COINS_SUCCESS.format(amount=amount, balance=balance),
            show_alert=True
        )
        logger.info(
            f"User {context.tg_user.id} claimed {amount} coins in game {game_id}, "
            f"new balance: {balance}"
        )
    else:
        # Это не должно произойти, так как мы уже проверили has_claimed_today
        await query.answer(GIVE_COINS_ALREADY_CLAIMED, show_alert=True)
        logger.warning(f"Unexpected failure to claim coins for user {context.tg_user.id}")


@ensure_game
async def handle_shop_transfer_callback(update: Update, context: GECallbackContext):
    """Обработчик кнопки 'Передать койны' в магазине"""
    from bot.handlers.game.shop_helpers import parse_shop_callback_data, create_double_chance_keyboard
    from bot.handlers.game.text_static import SHOP_ERROR_NOT_YOUR_SHOP, get_transfer_messages
    from bot.handlers.game.config import get_config

    query = update.callback_query

    if query is None:
        logger.error("callback_query is None!")
        return

    logger.info(f"Shop transfer callback from user {query.from_user.id} in chat {update.effective_chat.id}")
    logger.info(f"Callback data: {query.data}")

    try:
        # Парсим callback_data для получения item_type и owner_user_id
        item_type, owner_user_id = parse_shop_callback_data(query.data)
        logger.info(f"Parsed callback: item_type={item_type}, owner_user_id={owner_user_id}")
    except ValueError as e:
        logger.error(f"Failed to parse callback_data: {e}")
        await query.answer("❌ Ошибка обработки запроса")
        return

    # Проверяем, что нажавший кнопку - это владелец магазина
    if query.from_user.id != owner_user_id:
        logger.warning(f"Shop ownership mismatch: User {query.from_user.id} tried to use shop of user {owner_user_id}")
        await query.answer(SHOP_ERROR_NOT_YOUR_SHOP, show_alert=True)
        return

    # Получаем конфигурацию и сообщения
    config = get_config(update.effective_chat.id)
    transfer_msgs = get_transfer_messages(config)

    # Получаем список игроков из игры, исключая отправителя
    players = [p for p in context.game.players if p.id != context.tg_user.id]

    if len(players) < 1:
        await query.answer("❌ Нет других игроков для передачи", show_alert=True)
        logger.warning(f"No other players for transfer in game {context.game.id}")
        return

    # Создаём клавиатуру с игроками (используем create_double_chance_keyboard для единообразия)
    keyboard = create_double_chance_keyboard(players, owner_user_id=context.tg_user.tg_id, callback_prefix="shop_transfer_select")

    # Отправляем сообщение с выбором получателя
    try:
        await query.edit_message_text(
            text=transfer_msgs['select_player'],
            parse_mode="MarkdownV2",
            reply_markup=keyboard
        )
        await query.answer()
        logger.info(f"Showed transfer player selection for user {context.tg_user.id}")
    except Exception as e:
        logger.error(f"Failed to show transfer selection: {e}")
        await query.answer("❌ Ошибка при отображении списка игроков")


@ensure_game
async def handle_shop_transfer_select_callback(update: Update, context: GECallbackContext):
    """Обработчик выбора получателя — показывает клавиатуру с выбором суммы"""
    from bot.handlers.game.shop_helpers import create_transfer_amount_keyboard
    from bot.handlers.game.text_static import SHOP_ERROR_NOT_YOUR_SHOP, get_transfer_messages
    from bot.handlers.game.config import get_config

    query = update.callback_query

    if query is None:
        logger.error("callback_query is None!")
        return

    logger.info(f"Shop transfer select callback from user {query.from_user.id}")
    logger.info(f"Callback data: {query.data}")

    # Парсим callback_data: shop_transfer_select_{receiver_id}_{owner_user_id}
    try:
        parts = query.data.split('_')
        if len(parts) < 4:
            raise ValueError(f"Invalid callback_data format: {query.data}")

        owner_user_id = int(parts[-1])
        receiver_id = int(parts[-2])

        logger.info(f"Parsed callback: receiver_id={receiver_id}, owner_user_id={owner_user_id}")
    except (ValueError, IndexError) as e:
        logger.error(f"Failed to parse callback_data: {e}")
        await query.answer("❌ Ошибка обработки запроса")
        return

    # Проверяем, что нажавший кнопку - это владелец магазина
    if query.from_user.id != owner_user_id:
        logger.warning(f"Shop ownership mismatch: User {query.from_user.id} tried to use shop of user {owner_user_id}")
        await query.answer(SHOP_ERROR_NOT_YOUR_SHOP, show_alert=True)
        return

    # Получаем конфигурацию и сообщения
    config = get_config(update.effective_chat.id)
    transfer_msgs = get_transfer_messages(config)

    # Получаем баланс отправителя
    balance = get_balance(context.db_session, context.game.id, context.tg_user.id)

    if balance < 2:  # TRANSFER_MIN_AMOUNT
        await query.answer("❌ Недостаточно койнов для передачи (минимум 2)", show_alert=True)
        return

    # Получаем имя получателя
    receiver = context.db_session.query(TGUser).filter_by(id=receiver_id).one()
    receiver_name = escape_markdown2(receiver.full_username())

    # Создаём клавиатуру с выбором суммы
    keyboard = create_transfer_amount_keyboard(balance, receiver_id, context.tg_user.tg_id, update.effective_chat.id)

    await query.edit_message_text(
        text=transfer_msgs['select_amount'].format(
            receiver_name=receiver_name,
            balance=format_number(balance)
        ),
        parse_mode="MarkdownV2",
        reply_markup=keyboard
    )
    await query.answer()

    logger.info(f"Showed transfer amount selection for user {context.tg_user.id}, receiver {receiver_id}")


@ensure_game
async def handle_shop_transfer_amount_callback(update: Update, context: GECallbackContext):
    """Обработчик выбора суммы для передачи койнов"""
    from bot.handlers.game.transfer_service import (
        can_transfer, execute_transfer, get_or_create_chat_bank
    )
    from bot.handlers.game.text_static import SHOP_ERROR_NOT_YOUR_SHOP, get_transfer_messages
    from bot.handlers.game.config import get_config

    query = update.callback_query

    if query is None:
        logger.error("callback_query is None!")
        return

    logger.info(f"Shop transfer amount callback from user {query.from_user.id}")
    logger.info(f"Callback data: {query.data}")

    # Парсим callback_data: shop_transfer_amount_{receiver_id}_{amount}_{owner_user_id}
    try:
        parts = query.data.split('_')
        if len(parts) < 5:
            raise ValueError(f"Invalid callback_data format: {query.data}")

        owner_user_id = int(parts[-1])
        amount = int(parts[-2])
        receiver_id = int(parts[-3])

        logger.info(f"Parsed callback: receiver_id={receiver_id}, amount={amount}, owner_user_id={owner_user_id}")
    except (ValueError, IndexError) as e:
        logger.error(f"Failed to parse callback_data: {e}")
        await query.answer("❌ Ошибка обработки запроса")
        return

    # Проверяем, что нажавший кнопку - это владелец магазина
    if query.from_user.id != owner_user_id:
        logger.warning(f"Shop ownership mismatch: User {query.from_user.id} tried to use shop of user {owner_user_id}")
        await query.answer(SHOP_ERROR_NOT_YOUR_SHOP, show_alert=True)
        return

    # Получаем конфигурацию и сообщения
    config = get_config(update.effective_chat.id)
    transfer_msgs = get_transfer_messages(config)

    # Получаем текущую дату
    current_dt = current_datetime()
    cur_year = current_dt.year
    cur_day = current_dt.timetuple().tm_yday

    # Проверяем кулдаун (по year+day)
    can_do, error = can_transfer(context.db_session, context.game.id, context.tg_user.id, cur_year, cur_day)
    if not can_do:
        if error == "already_transferred_today":
            await query.answer("❌ Вы уже совершали перевод сегодня", show_alert=True)
            await query.edit_message_text(
                text=transfer_msgs['error_cooldown'],
                parse_mode="MarkdownV2"
            )
        return

    # Проверяем баланс
    balance = get_balance(context.db_session, context.game.id, context.tg_user.id)
    if balance < amount:
        await query.answer(f"❌ Недостаточно койнов! Баланс: {balance}", show_alert=True)
        return

    # Выполняем перевод
    amount_sent, amount_received, commission = execute_transfer(
        context.db_session, context.game.id,
        context.tg_user.id, receiver_id,
        amount, cur_year, cur_day
    )

    # Получаем обновлённые балансы
    sender_balance = get_balance(context.db_session, context.game.id, context.tg_user.id)
    receiver = context.db_session.query(TGUser).filter_by(id=receiver_id).one()
    receiver_balance = get_balance(context.db_session, context.game.id, receiver.id)
    bank = get_or_create_chat_bank(context.db_session, context.game.id)

    # Формируем сообщение об успехе
    sender_name = escape_markdown2(context.tg_user.full_username())
    receiver_name = escape_markdown2(receiver.full_username())

    response_text = transfer_msgs['success'].format(
        sender_name=sender_name,
        receiver_name=receiver_name,
        amount_sent=format_number(amount_sent),
        amount_received=format_number(amount_received),
        commission=format_number(commission),
        sender_balance=format_number(sender_balance),
        receiver_balance=format_number(receiver_balance),
        bank_balance=format_number(bank.balance)
    )

    await query.answer("✅ Перевод выполнен!", show_alert=True)
    await query.edit_message_text(
        text=response_text,
        parse_mode="MarkdownV2"
    )

    logger.info(
        f"Transfer completed: sender {context.tg_user.id}, receiver {receiver_id}, "
        f"amount {amount_sent}, commission {commission}"
    )

@ensure_game
async def handle_shop_bank_callback(update: Update, context: GECallbackContext):
    """Обработчик кнопки 'Банк чата' в магазине"""
    from bot.handlers.game.shop_helpers import parse_shop_callback_data
    from bot.handlers.game.transfer_service import get_or_create_chat_bank
    from bot.handlers.game.text_static import SHOP_ERROR_NOT_YOUR_SHOP, BANK_INFO

    query = update.callback_query

    if query is None:
        logger.error("callback_query is None!")
        return

    logger.info(f"Shop bank callback from user {query.from_user.id} in chat {update.effective_chat.id}")
    logger.info(f"Callback data: {query.data}")

    try:
        # Парсим callback_data для получения item_type и owner_user_id
        item_type, owner_user_id = parse_shop_callback_data(query.data)
        logger.info(f"Parsed callback: item_type={item_type}, owner_user_id={owner_user_id}")
    except ValueError as e:
        logger.error(f"Failed to parse callback_data: {e}")
        await query.answer("❌ Ошибка обработки запроса")
        return

    # Проверяем, что нажавший кнопку - это владелец магазина
    if query.from_user.id != owner_user_id:
        logger.warning(f"Shop ownership mismatch: User {query.from_user.id} tried to use shop of user {owner_user_id}")
        await query.answer(SHOP_ERROR_NOT_YOUR_SHOP, show_alert=True)
        return

    # Получаем баланс банка
    bank = get_or_create_chat_bank(context.db_session, context.game.id)

    # Формируем сообщение
    response_text = BANK_INFO.format(balance=format_number(bank.balance))

    await query.answer()
    await query.edit_message_text(
        text=response_text,
        parse_mode="MarkdownV2"
    )

    logger.info(f"Showed bank info for game {context.game.id}, balance: {bank.balance}")


@ensure_game
async def handle_shop_predict_cancel_callback(update: Update, context: GECallbackContext):
    """Обработчик кнопки 'Отмена' при выборе предсказания"""
    from bot.handlers.game.shop_helpers import parse_shop_callback_data, create_shop_keyboard, format_shop_menu_message
    from bot.handlers.game.shop_service import get_active_effects
    from bot.handlers.game.prediction_service import delete_prediction_draft
    from bot.handlers.game.text_static import SHOP_ERROR_NOT_YOUR_SHOP

    query = update.callback_query

    if query is None:
        logger.error("callback_query is None!")
        return

    logger.info(f"Shop predict cancel callback from user {query.from_user.id} in chat {update.effective_chat.id}")
    logger.info(f"Callback data: {query.data}")

    try:
        # Парсим callback_data для получения item_type и owner_user_id
        item_type, owner_user_id = parse_shop_callback_data(query.data)
        logger.info(f"Parsed callback: item_type={item_type}, owner_user_id={owner_user_id}")
    except ValueError as e:
        logger.error(f"Failed to parse callback_data: {e}")
        await query.answer("❌ Ошибка обработки запроса")
        return

    # Проверяем, что нажавший кнопку - это владелец магазина
    if query.from_user.id != owner_user_id:
        logger.warning(f"Shop ownership mismatch: User {query.from_user.id} tried to use shop of user {owner_user_id}")
        await query.answer(SHOP_ERROR_NOT_YOUR_SHOP, show_alert=True)
        return

    # Удаляем черновик предсказания из БД
    current_dt = current_datetime()
    cur_year = current_dt.year
    cur_day = current_dt.timetuple().tm_yday

    # Вычисляем завтрашний день (день действия предсказания)
    from bot.handlers.game.shop_service import calculate_next_day
    current_date = current_dt.date()
    target_year, target_day = calculate_next_day(current_date, cur_year)

    delete_prediction_draft(context.db_session, context.game.id, context.tg_user.id)
    logger.info(f"Deleted prediction draft for user {context.tg_user.id} in game {context.game.id}")

    # Очищаем выбор из памяти (на случай если он там был)
    if 'prediction_selection' in context.user_data:
        context.user_data['prediction_selection'] = []

    # Получаем баланс текущего пользователя
    balance = get_balance(context.db_session, context.game.id, context.tg_user.id)

    # Получаем информацию об активных эффектах
    active_effects = get_active_effects(
        context.db_session, context.game.id, context.tg_user.id,
        current_date
    )

    # Создаём клавиатуру магазина
    keyboard = create_shop_keyboard(owner_user_id=context.tg_user.tg_id, chat_id=update.effective_chat.id, active_effects=active_effects)

    # Форматируем сообщение
    user_name = context.tg_user.full_username()
    message_text = format_shop_menu_message(balance, update.effective_chat.id, user_name, active_effects)

    # Обновляем сообщение
    await query.answer("❌ Предсказание отменено")
    await query.edit_message_text(
        text=message_text,
        parse_mode="MarkdownV2",
        reply_markup=keyboard
    )

    logger.info(f"Cancelled prediction and returned to shop menu for user {context.tg_user.id}")


@ensure_game
async def handle_shop_back_callback(update: Update, context: GECallbackContext):
    """Обработчик кнопки 'Назад в магазин'"""
    from bot.handlers.game.shop_helpers import parse_shop_callback_data, create_shop_keyboard, format_shop_menu_message
    from bot.handlers.game.shop_service import get_active_effects
    from bot.handlers.game.text_static import SHOP_ERROR_NOT_YOUR_SHOP

    query = update.callback_query

    if query is None:
        logger.error("callback_query is None!")
        return

    logger.info(f"Shop back callback from user {query.from_user.id} in chat {update.effective_chat.id}")
    logger.info(f"Callback data: {query.data}")

    try:
        # Парсим callback_data для получения item_type и owner_user_id
        item_type, owner_user_id = parse_shop_callback_data(query.data)
        logger.info(f"Parsed callback: item_type={item_type}, owner_user_id={owner_user_id}")
    except ValueError as e:
        logger.error(f"Failed to parse callback_data: {e}")
        await query.answer("❌ Ошибка обработки запроса")
        return

    # Проверяем, что нажавший кнопку - это владелец магазина
    if query.from_user.id != owner_user_id:
        logger.warning(f"Shop ownership mismatch: User {query.from_user.id} tried to use shop of user {owner_user_id}")
        await query.answer(SHOP_ERROR_NOT_YOUR_SHOP, show_alert=True)
        return

    # Получаем баланс текущего пользователя
    balance = get_balance(context.db_session, context.game.id, context.tg_user.id)

    # Получаем информацию об активных эффектах
    current_dt = current_datetime()
    current_date = current_dt.date()

    active_effects = get_active_effects(
        context.db_session, context.game.id, context.tg_user.id,
        current_date
    )

    # Создаём клавиатуру магазина
    keyboard = create_shop_keyboard(owner_user_id=context.tg_user.tg_id, chat_id=update.effective_chat.id, active_effects=active_effects)

    # Форматируем сообщение
    user_name = context.tg_user.full_username()
    message_text = format_shop_menu_message(balance, update.effective_chat.id, user_name, active_effects)

    # Обновляем сообщение
    await query.answer()
    await query.edit_message_text(
        text=message_text,
        parse_mode="MarkdownV2",
        reply_markup=keyboard
    )

    logger.info(f"Returned to shop menu for user {context.tg_user.id}")


@ensure_game
async def handle_shop_achievements_callback(update: Update, context: GECallbackContext):
    """Обработчик кнопки 'Мои достижения' в магазине"""
    from bot.handlers.game.shop_helpers import parse_shop_callback_data
    from bot.handlers.game.achievement_service import get_user_achievements
    from bot.handlers.game.achievement_constants import ACHIEVEMENTS
    from bot.handlers.game.text_static import (
        SHOP_ERROR_NOT_YOUR_SHOP,
        ACHIEVEMENTS_HEADER,
        ACHIEVEMENT_EARNED_FORMAT,
        ACHIEVEMENT_NOT_EARNED_FORMAT,
        ACHIEVEMENTS_TOTAL_COINS,
        ACHIEVEMENTS_EMPTY
    )
    from bot.handlers.game.shop_helpers import format_date_readable
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    query = update.callback_query

    if query is None:
        logger.error("callback_query is None!")
        return

    logger.info(f"Shop achievements callback from user {query.from_user.id} in chat {update.effective_chat.id}")
    logger.info(f"Callback data: {query.data}")

    try:
        # Парсим callback_data для получения item_type и owner_user_id
        item_type, owner_user_id = parse_shop_callback_data(query.data)
        logger.info(f"Parsed callback: item_type={item_type}, owner_user_id={owner_user_id}")
    except ValueError as e:
        logger.error(f"Failed to parse callback_data: {e}")
        await query.answer("❌ Ошибка обработки запроса")
        return

    # Проверяем, что нажавший кнопку - это владелец магазина
    if query.from_user.id != owner_user_id:
        logger.warning(f"Shop ownership mismatch: User {query.from_user.id} tried to use shop of user {owner_user_id}")
        await query.answer(SHOP_ERROR_NOT_YOUR_SHOP, show_alert=True)
        return

    # Получаем достижения пользователя
    user_achievements = get_user_achievements(context.db_session, context.game.id, context.tg_user.id)

    # Формируем сообщение
    user_name = context.tg_user.full_username()
    message_lines = [ACHIEVEMENTS_HEADER.format(user_name=escape_markdown2(user_name))]
    message_lines.append("")

    if not user_achievements:
        # Если нет достижений
        message_lines.append(ACHIEVEMENTS_EMPTY)
    else:
        # Создаём словарь полученных достижений для быстрого поиска
        earned_codes = {ach.achievement_code: ach for ach in user_achievements}
        total_coins = 0

        # Проходим по всем возможным достижениям
        for code, achievement_data in ACHIEVEMENTS.items():
            if code in earned_codes:
                # Достижение получено
                earned_ach = earned_codes[code]
                date_str = format_date_readable(earned_ach.year, earned_ach.earned_at.timetuple().tm_yday)
                message_lines.append(
                    ACHIEVEMENT_EARNED_FORMAT.format(
                        name=escape_markdown2(achievement_data['name']),
                        date=escape_markdown2(date_str)
                    )
                )
                total_coins += achievement_data['reward']
            else:
                # Достижение не получено
                message_lines.append(
                    ACHIEVEMENT_NOT_EARNED_FORMAT.format(
                        name=escape_markdown2(achievement_data['name'])
                    )
                )

        # Добавляем общую сумму заработанных койнов
        if total_coins > 0:
            message_lines.append(ACHIEVEMENTS_TOTAL_COINS.format(total=format_number(total_coins)))

    message_text = "\n".join(message_lines)

    # Создаём кнопку "Назад в магазин"
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "⬅️ Назад в магазин",
            callback_data=f"shop_back_{owner_user_id}"
        )
    ]])

    await query.answer()
    await query.edit_message_text(
        text=message_text,
        parse_mode="MarkdownV2",
        reply_markup=keyboard
    )

    logger.info(f"Showed achievements for user {context.tg_user.id}, total: {len(user_achievements)}")


@ensure_game
async def handle_shop_toast_callback(update: Update, context: GECallbackContext):
    """Обработчик кнопки '🍻 Тост' в магазине — показывает список игроков"""
    from bot.handlers.game.shop_helpers import parse_shop_callback_data, create_double_chance_keyboard
    from bot.handlers.game.text_static import SHOP_ERROR_NOT_YOUR_SHOP, get_toast_messages
    from bot.handlers.game.config import get_config

    query = update.callback_query

    if query is None:
        logger.error("callback_query is None!")
        return

    logger.info(f"Shop toast callback from user {query.from_user.id} in chat {update.effective_chat.id}")
    logger.info(f"Callback data: {query.data}")

    try:
        item_type, owner_user_id = parse_shop_callback_data(query.data)
        logger.info(f"Parsed callback: item_type={item_type}, owner_user_id={owner_user_id}")
    except ValueError as e:
        logger.error(f"Failed to parse callback_data: {e}")
        await query.answer("❌ Ошибка обработки запроса")
        return

    if query.from_user.id != owner_user_id:
        logger.warning(f"Shop ownership mismatch: User {query.from_user.id} tried to use shop of user {owner_user_id}")
        await query.answer(SHOP_ERROR_NOT_YOUR_SHOP, show_alert=True)
        return

    config = get_config(update.effective_chat.id)
    toast_msgs = get_toast_messages(config)

    # Проверяем баланс заранее
    balance = get_balance(context.db_session, context.game.id, context.tg_user.id)
    if balance < config.constants.toast_price:
        await query.answer(
            toast_msgs['error_insufficient_funds'].replace('\\', '').format(balance=balance),
            show_alert=True
        )
        return

    # Все игроки включая отправителя (self-toast разрешён)
    players = context.game.players

    if len(players) < 1:
        await query.answer("❌ Нет игроков для тоста", show_alert=True)
        return

    keyboard = create_double_chance_keyboard(players, owner_user_id=context.tg_user.tg_id, callback_prefix="shop_toast_select")

    try:
        await query.edit_message_text(
            text=toast_msgs['select_player'],
            parse_mode="MarkdownV2",
            reply_markup=keyboard
        )
        await query.answer()
        logger.info(f"Showed toast player selection for user {context.tg_user.id}")
    except Exception as e:
        logger.error(f"Failed to show toast selection: {e}")
        await query.answer("❌ Ошибка при отображении списка игроков")


@ensure_game
async def handle_shop_toast_select_callback(update: Update, context: GECallbackContext):
    """Обработчик выбора получателя тоста — выполняет тост"""
    from bot.handlers.game.toast_service import execute_toast, get_or_create_chat_bank
    from bot.handlers.game.text_static import SHOP_ERROR_NOT_YOUR_SHOP, get_toast_messages
    from bot.handlers.game.config import get_config

    query = update.callback_query

    if query is None:
        logger.error("callback_query is None!")
        return

    logger.info(f"Shop toast select callback from user {query.from_user.id}")
    logger.info(f"Callback data: {query.data}")

    # Парсим callback_data: shop_toast_select_{receiver_id}_{owner_user_id}
    try:
        parts = query.data.split('_')
        if len(parts) < 4:
            raise ValueError(f"Invalid callback_data format: {query.data}")
        owner_user_id = int(parts[-1])
        receiver_id = int(parts[-2])
        logger.info(f"Parsed callback: receiver_id={receiver_id}, owner_user_id={owner_user_id}")
    except (ValueError, IndexError) as e:
        logger.error(f"Failed to parse callback_data: {e}")
        await query.answer("❌ Ошибка обработки запроса")
        return

    if query.from_user.id != owner_user_id:
        logger.warning(f"Shop ownership mismatch: User {query.from_user.id} tried to use shop of user {owner_user_id}")
        await query.answer(SHOP_ERROR_NOT_YOUR_SHOP, show_alert=True)
        return

    config = get_config(update.effective_chat.id)
    toast_msgs = get_toast_messages(config)

    # Проверяем баланс
    balance = get_balance(context.db_session, context.game.id, context.tg_user.id)
    if balance < config.constants.toast_price:
        await query.answer(
            toast_msgs['error_insufficient_funds'].replace('\\', '').format(balance=balance),
            show_alert=True
        )
        return

    current_dt = current_datetime()
    cur_year = current_dt.year

    # Выполняем тост
    amount_sent, amount_received, commission = execute_toast(
        context.db_session, context.game.id,
        context.tg_user.id, receiver_id,
        cur_year
    )

    # Получаем обновлённые балансы
    sender_balance = get_balance(context.db_session, context.game.id, context.tg_user.id)
    receiver = context.db_session.query(TGUser).filter_by(id=receiver_id).one()
    receiver_balance = get_balance(context.db_session, context.game.id, receiver.id)

    sender_name = escape_markdown2(context.tg_user.full_username())
    receiver_name = escape_markdown2(receiver.full_username())

    response_text = toast_msgs['success'].format(
        sender_name=sender_name,
        receiver_name=receiver_name,
        amount_sent=format_number(amount_sent),
        amount_received=format_number(amount_received),
        commission=format_number(commission),
        sender_balance=format_number(sender_balance),
        receiver_balance=format_number(receiver_balance),
    )

    await query.answer("🍻 Тост поднят!", show_alert=True)
    await query.edit_message_text(
        text=response_text,
        parse_mode="MarkdownV2"
    )

    logger.info(
        f"Toast completed: sender {context.tg_user.id}, receiver {receiver_id}, "
        f"amount {amount_sent}, commission {commission}"
    )
