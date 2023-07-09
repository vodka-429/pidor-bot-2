import functools
import logging
import random
import time
from datetime import datetime
from typing import List
from zoneinfo import ZoneInfo

from sqlalchemy import func, text
from sqlmodel import select
from telegram import Update, ParseMode
from telegram.ext import CallbackContext

from bot.app.models import Game, GamePlayer, TGUser, GameResult
from bot.handlers.game.phrases import stage1, stage2, stage3, stage4
from bot.handlers.game.text_static import STATS_PERSONAL, \
    STATS_CURRENT_YEAR, \
    STATS_ALL_TIME, STATS_LIST_ITEM, REGISTRATION_SUCCESS, \
    ERROR_ALREADY_REGISTERED, ERROR_ZERO_PLAYERS, ERROR_NOT_ENOUGH_PLAYERS, \
    REMOVE_REGISTRATION, CURRENT_DAY_GAME_RESULT, REMOVE_REGISTRATION_ERROR
from bot.utils import escape_markdown2, ECallbackContext

GAME_RESULT_TIME_DELAY = 2

MOSCOW_TZ = ZoneInfo('Europe/Moscow')


def current_year_day():
    now = datetime.now(tz=MOSCOW_TZ)
    return now.year, now.timetuple().tm_yday


class GECallbackContext(ECallbackContext):
    """Extended bot context with additional game `Game` field"""
    game: Game


def ensure_game(func):
    def wrapper(update: Update, context: ECallbackContext):
        game: Game = context.db_session.query(Game).filter_by(chat_id=update.effective_chat.id).one_or_none()
        if game is None:
            game = Game(chat_id=update.effective_chat.id)
            context.db_session.add(game)
            context.db_session.commit()
            context.db_session.refresh(game)
        context.game = game
        return func(update, context)

    return wrapper


# PIDOR Game
@ensure_game
def pidor_cmd(update: Update, context: GECallbackContext):
    logging.info("Game of the day started")
    players: List[TGUser] = context.game.players

    if len(players) < 2:
        update.effective_chat.send_message(ERROR_NOT_ENOUGH_PLAYERS)
        return

    cur_year, cur_day = current_year_day()
    game_result: GameResult = context.db_session.query(GameResult).filter_by(game_id=context.game.id, year=cur_year, day=cur_day).one_or_none()
    if game_result:
        update.message.reply_markdown_v2(
            CURRENT_DAY_GAME_RESULT.format(
                username=escape_markdown2(game_result.winner.full_username())))
    else:
        winner: TGUser = random.choice(players)
        context.game.results.append(GameResult(game_id=context.game.id, year=cur_year, day=cur_day, winner=winner))
        context.db_session.commit()

        update.effective_chat.send_message(random.choice(stage1.phrases))
        time.sleep(GAME_RESULT_TIME_DELAY)
        update.effective_chat.send_message(random.choice(stage2.phrases))
        time.sleep(GAME_RESULT_TIME_DELAY)
        update.effective_chat.send_message(random.choice(stage3.phrases))
        time.sleep(GAME_RESULT_TIME_DELAY)
        update.effective_chat.send_message(random.choice(stage4.phrases).format(
            username=winner.full_username(mention=True)))


def pidorules_cmd(update: Update, _context: CallbackContext):
    logging.info("Game rules requested")
    update.effective_chat.send_message(
        "Правила игры *Пидор Дня* \(только для групповых чатов\):\n"
        "*1\.* Зарегистрируйтесь в игру по команде */pidoreg*\n"
        "*2\.* Подождите пока зарегиструются все \(или большинство :\)\n"
        "*3\.* Запустите розыгрыш по команде */pidor*\n"
        "*4\.* Просмотр статистики канала по команде */pidorstats*, */pidorall*\n"
        "*5\.* Личная статистика по команде */pidorme*\n"
        "*6\.* Статистика за последний год по комнаде */pidor2020* \(так же есть за 2016\-2020\)\n"
        "*7\. \(\!\!\! Только для администраторов чатов\)*: удалить из игры может только Админ канала, сначала выведя по команде список игроков: */pidormin* list\n"
        "Удалить же игрока можно по команде \(используйте идентификатор пользователя \- цифры из списка пользователей\): */pidormin* del 123456\n"
        "\n"
        "*Важно*, розыгрыш проходит только *раз в день*, повторная команда выведет *результат* игры\.\n"
        "\n"
        "Сброс розыгрыша происходит каждый день в 12 часов ночи по UTC\+2 \(примерно в два часа ночи по Москве\)\.\n\n"
        "Поддержать бота можно по [ссылке](https://github.com/unaimillan/sublime-telegram-bot) :\)"
        , parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)


@ensure_game
def pidoreg_cmd(update: Update, context: GECallbackContext):
    players: List[TGUser] = context.game.players

    if len(players) == 0:
        update.effective_chat.send_message(
            ERROR_ZERO_PLAYERS.format(username=update.message.from_user.name))

    if context.tg_user not in context.game.players:
        context.game.players.append(context.tg_user)
        context.db_session.commit()
        update.effective_message.reply_markdown_v2(REGISTRATION_SUCCESS)
    else:
        update.effective_message.reply_markdown_v2(ERROR_ALREADY_REGISTERED)


@ensure_game
def pidorunreg_cmd(update: Update, context: GECallbackContext):
    if context.tg_user in context.game.players:
        context.game.players.remove(context.tg_user)
        context.db_session.commit()
        update.effective_message.reply_markdown_v2(REMOVE_REGISTRATION)
    else:
        update.effective_message.reply_markdown_v2(REMOVE_REGISTRATION_ERROR)


def build_player_table(player_list: list[tuple[TGUser, int]]) -> str:
    result = []
    for number, (tg_user, amount) in enumerate(player_list, 1):
        result.append(STATS_LIST_ITEM.format(number=number,
                                             username=escape_markdown2(tg_user.full_username()),
                                             amount=amount))
    return ''.join(result)


@ensure_game
def pidorstats_cmd(update: Update, context: GECallbackContext):
    cur_year, _ = current_year_day()
    stmt = select(TGUser, func.count(GameResult.winner_id).label('count')) \
        .join(TGUser, GameResult.winner_id == TGUser.id) \
        .filter(GameResult.game_id == context.game.id, GameResult.year == cur_year) \
        .group_by(TGUser) \
        .order_by(text('count DESC'))
    db_results = context.db_session.exec(stmt).all()

    player_table = build_player_table(db_results)
    answer = STATS_CURRENT_YEAR.format(player_stats=player_table,
                                       player_count=len(context.game.players))
    update.effective_chat.send_message(answer, parse_mode=ParseMode.MARKDOWN_V2)


@ensure_game
def pidorall_cmd(update: Update, context: GECallbackContext):
    stmt = select(TGUser, func.count(GameResult.winner_id).label('count')) \
        .join(TGUser, GameResult.winner_id == TGUser.id) \
        .filter(GameResult.game_id == context.game.id) \
        .group_by(TGUser) \
        .order_by(text('count DESC'))
    db_results = context.db_session.exec(stmt).all()

    player_table = build_player_table(db_results)
    answer = STATS_ALL_TIME.format(player_stats=player_table,
                                       player_count=len(context.game.players))
    update.effective_chat.send_message(answer, parse_mode=ParseMode.MARKDOWN_V2)


@ensure_game
def pidorme_cmd(update: Update, context: GECallbackContext):
    cur_year, _ = current_year_day()
    stmt = select(TGUser, func.count(GameResult.winner_id).label('count')) \
        .join(TGUser, GameResult.winner_id == TGUser.id) \
        .filter(GameResult.game_id == context.game.id, GameResult.winner_id == context.tg_user.id) \
        .group_by(TGUser) \
        .order_by(text('count DESC'))
    tg_user, count = context.db_session.exec(stmt).one()

    update.effective_chat.send_message(STATS_PERSONAL.format(
        username=tg_user.full_username(), amount=count),
        parse_mode=ParseMode.MARKDOWN_V2)
