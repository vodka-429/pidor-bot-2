"""Статические текстовые сообщения для игры."""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.handlers.game.config import ChatConfig

REGISTRATION_SUCCESS = """*OK\!* Ты теперь участвуешь в игре "*Пидор Дня*"\!"""
REGISTRATION_MANY_SUCCESS = """*OK\!* {username} теперь участвует в игре "*Пидор Дня*"\!"""
ERROR_ALREADY_REGISTERED = """Эй\, ты уже в игре\!"""
ERROR_ALREADY_REGISTERED_MANY = """Эй\, {username} уже в игре\!"""
REMOVE_REGISTRATION = """*OK\!* Ты больше *не* участвуешь в игре "*Пидор Дня*"\!\n_P\.S\. Но всё равно пидор\!_"""
REMOVE_REGISTRATION_ERROR = """Ээээ\, тьфу\, ты и так не зарегестрирован\!"""
CURRENT_DAY_GAME_RESULT = """Согласно моей информации, по результатам сегодняшнего розыгрыша *пидор дня* \- {username}\!"""
STATS_ALL_TIME = """Топ\-50 *пидоров* за все время:\n\n{player_stats}\nВсего участников — {player_count}"""
STATS_CURRENT_YEAR = """Топ\-50 *пидоров* за текущий год\:\n\n{player_stats}\nВсего участников — {player_count}"""
STATS_LIST_ITEM = """*{number}\.* {username} — {amount} раз\\(а\\)\n"""
STATS_PERSONAL = """{username}, ты был\\(а\\) *пидором дня* — _{amount}_ раз\\!"""
YEAR_RESULTS_ANNOUNCEMENT = """Йо\-хо\-хо\! __С Новым Годом__\! Узнай\, кто же стал пидором {year} года: /pidor{year}"""
YEAR_RESULTS_MSG = """*Пидор {year} года* — {username}\!\n\nТоп\-50 пидоров за {year} год:\n\n{player_list}\n"""
ERROR_NOT_ENOUGH_PLAYERS = """Нужно как минимум два игрока, чтобы начать игру! Зарегистрируйся используя /pidoreg"""
ERROR_ZERO_PLAYERS = """Зарегистрированных в игру еще нет, а значит пидор ты - {username}!"""

# Tie-breaker сообщения
TIEBREAKER_ANNOUNCEMENT = """🎲 *TIE\\-BREAKER\\!*

Обнаружено *{count}* лидеров года с одинаковым счётом\\!

Лидеры: {leaders}

Запускаем дополнительный розыгрыш для определения единственного победителя года\\.\\.\\. 🏆"""

TIEBREAKER_RESULT = """🏆 *ПОБЕДИТЕЛЬ {year} ГОДА\\!*

После напряжённого tie\\-breaker розыгрыша победителем года становится:

*{username}*

Поздравляем\\! 🎉"""

# Драматические сообщения о пропущенных днях
MISSED_DAYS_1 = """⚠️ *Внимание\!* Вчера розыгрыш не проводился\.\.\. Кто\-то забыл про игру\? 🤔"""
MISSED_DAYS_2_3 = """⚠️ *Тревога\!* Прошло уже *{days}* дня без розыгрыша\! Неужели все забыли про священный ритуал\? 😱"""
MISSED_DAYS_4_7 = """🚨 *ВНИМАНИЕ\!* Уже *{days}* дней без розыгрыша\! Это начинает напоминать катастрофу\.\.\. Традиция в опасности\! 😨"""
MISSED_DAYS_8_14 = """🔥 *КРИТИЧЕСКАЯ СИТУАЦИЯ\!* *{days}* дней без розыгрыша\! Игра на грани исчезновения\! Кто\-нибудь\, спасите традицию\! 🆘"""
MISSED_DAYS_15_30 = """💀 *КАТАСТРОФА\!* Прошло уже *{days}* дней\!\!\! Игра практически мертва\! Это конец эпохи\? Неужели никто не помнит о великой традиции\?\! 😭"""
MISSED_DAYS_31_PLUS = """☠️ *АПОКАЛИПСИС\!* *{days}* дней без розыгрыша\!\!\! Игра превратилась в легенду\, в миф\.\.\. Но сегодня \- день возрождения\! Феникс восстаёт из пепла\! 🔥🦅"""

# Сообщения для финального голосования
FINAL_VOTING_MESSAGE = """🎭 *Финальное голосование года\!*

В этом году было пропущено *{missed_days}* дней розыгрыша\. Ну и пидоры же вы\!

Настало время справедливости\! Начинается *взвешенное голосование*\, где вес каждого голоса зависит от количества побед в этом году\. Чем больше раз ты был пидором \- тем больше твой голос весит\.

*Веса игроков \(кто сколько раз был пидором\):*
{player_weights}

{excluded_leaders_info}

*Правила голосования:*
• Выберите кандидатов нажатием на кнопки\. Максимум *{max_votes}* выборов\.
• Результаты будут скрыты до завершения голосования\, которое продлится *24 часа*\.
{winner_text}

_Ваши голоса видны только вам\\. Результаты будут объявлены после завершения голосования\\._

Голосуйте мудро\! Или тупо\, как обычно\. 🗳️"""

FINAL_VOTING_RESULTS = """🏆 *Результаты финального голосования\!*

Ну что\, пидоры\, подсчитали\! Победители: *{winners}*\!

*Результаты голосования:*
{voting_results}

*Распределение пропущенных дней:*
{days_distribution}

Поздравляем победителей\! Или не поздравляем\, хз\. Главное \- справедливость восторжествовала\!

*Итоговая статистика года:*
{year_stats}"""

FINAL_VOTING_STATUS_NOT_STARTED = """ℹ️ Финальное голосование ещё не запущено\.

Голосование можно запустить 29 или 30 декабря командой /pidorfinal"""

FINAL_VOTING_STATUS_ACTIVE = """🗳️ *Финальное голосование активно\!*

Запущено: {started_at}
Пропущено дней: {missed_days}

Голосование завершается вручную командой /pidorfinalclose \(не ранее чем через 24 часа после старта\)

Голосование в процессе\.\.\."""

FINAL_VOTING_STATUS_ACTIVE_WITH_VOTERS = """🗳️ *Финальное голосование активно\!*

Запущено: {started_at}
Пропущено дней: {missed_days}
Проголосовало: {voters_count} игроков

Голосование завершается вручную командой /pidorfinalclose \(не ранее чем через 24 часа после старта\)

Голосование в процессе\.\.\."""

FINAL_VOTING_STATUS_COMPLETED = """✅ *Финальное голосование завершено\!*

Победители: *{winner}*
Завершено: {ended_at}
Распределено дней: {missed_days}

Всё\, можете расходиться\. Шоу окончено\!"""

# Сообщения для команды /pidormissed
MISSED_DAYS_INFO_WITH_LIST = """📊 *Пропущенные дни в этом году:*

Всего пропущено: *{count}* дней

Список пропущенных дней:
{days_list}"""

MISSED_DAYS_INFO_COUNT_ONLY = """📊 *Пропущенные дни в этом году:*

Всего пропущено: *{count}* дней

_Слишком много дней для отображения списка\._"""

# Ошибки финального голосования
FINAL_VOTING_ERROR_DATE = """❌ *Ошибка\!* Финальное голосование можно запустить только 29 или 30 декабря\!"""

FINAL_VOTING_ERROR_TOO_MANY = """❌ *Ошибка\!* Слишком много пропущенных дней \(*{count}*\)\! Финальное голосование доступно только при количестве пропущенных дней менее {max_days}\."""

FINAL_VOTING_ERROR_ALREADY_EXISTS = """❌ *Ошибка\!* Финальное голосование для этого года уже запущено\!

Проверьте статус: /pidorfinalstatus"""

FINAL_VOTING_CLOSE_SUCCESS = """✅ Голосование завершено\\! Подсчитываем результаты\\.\\.\\.

Сейчас узнаем\, кто же главный пидор года\! Барабанная дробь\\.\\.\\. 🥁"""

FINAL_VOTING_CLOSE_ERROR_NOT_ADMIN = """❌ *Ошибка\\!* Завершить голосование может только администратор чата\\."""

FINAL_VOTING_CLOSE_ERROR_NOT_AUTHORIZED = """❌ *Ошибка\\!* Завершить голосование может только настоятель\\."""

FINAL_VOTING_CLOSE_ERROR_NOT_ACTIVE = """❌ *Ошибка\\!* Нет активного голосования для завершения\\."""

VOTING_ENDED_RESPONSE = "пішов в хуй"

# Сообщения для системы пидор-койнов
COIN_INFO = """\n\n<code>🎉 {winner_username}: +{amount} пидор-койн(ов)</code>\n<code>🎉 {executor_username}: +{executor_amount} пидор-койн(ов) за запуск команды</code>"""
COIN_INFO_SELF_PIDOR = """\n\n<code>🎉 Сам себе пидор! +{amount} пидор-койн(ов)</code>"""

# Сообщения для команд пидор-койнов
COINS_PERSONAL = """{username}, у тебя *{amount}* пидор\\-койн\\(ов\\)\\!"""
COINS_CURRENT_YEAR = """Топ\\-50 по *пидор\\-койнам* за текущий год\\:\n\n{player_stats}\nВсего участников — {player_count}"""
COINS_ALL_TIME = """Топ\\-50 по *пидор\\-койнам* за все время\\:\n\n{player_stats}\nВсего участников — {player_count}"""
COINS_LIST_ITEM = """*{number}\\.* {username} — {amount} койн\\(ов\\)\n"""
COIN_EARNED = """🎉 Поздравляем\\! Вы получили *{amount}* пидор\\-койн\\(ов\\) за победу в розыгрыше\\!"""


# Сообщения для магазина пидор-койнов
SHOP_MENU = """🏪 *Магазин пидор\\-койнов*

💰 Ваш баланс: *{balance}* койн\\(ов\\)

*Доступные товары:*

🛡️ *Защита от пидора* \\(10 койнов\\)
Защищает от выбора пидором на следующий день\\.
Кулдаун: 7 дней после использования\\.

🎲 *Двойной шанс* \\(8 койнов\\)
Удваивает ваш шанс стать пидором дня\\.
Действует до следующей победы\\.

🔮 *Предсказание* \\(3 койна\\)
Предскажите\, кто станет пидором дня\\.
Если угадаете \\- получите 30 койнов\\!

_Выберите товар нажатием на кнопку ниже\\._"""

SHOP_ITEM_IMMUNITY_DESC = "🛡️ Защита (10 койнов)"
SHOP_ITEM_DOUBLE_CHANCE_DESC = "🎲 Двойной шанс (8 койнов)"
SHOP_ITEM_PREDICTION_DESC = "🔮 Предсказание (3 койна)"

SHOP_ERROR_NOT_YOUR_SHOP = "❌ Это не твой магазин! Открой свой командой /pidorshop"

# Сообщения для защиты от пидора
IMMUNITY_PURCHASE_SUCCESS = """✅ *Защита куплена\\!*

Вы защищены от выбора пидором *{date}*\\.
Списано: 10 койнов
Комиссия в банк: {commission} 🪙
Новый баланс: {balance} койн\\(ов\\)"""

IMMUNITY_ERROR_INSUFFICIENT_FUNDS = "❌ Недостаточно средств\\! Нужно 10 койнов\\, у вас: {balance}"
IMMUNITY_ERROR_ALREADY_ACTIVE = "❌ Защита уже активна на *{date}*\\!"
IMMUNITY_ERROR_COOLDOWN = "❌ Защита на кулдауне\\! Можно использовать снова с *{date}*"
IMMUNITY_ACTIVATED_IN_GAME = "🛡️ <b>{username}</b> был(а) защищён(а) от выбора! Перевыбираем...\n\n<code>🎉 {username_plain}: +{amount} пидор-койн(ов) за спасение</code>"

# Сообщения для двойного шанса
DOUBLE_CHANCE_PURCHASE_SUCCESS_SELF = """✅ *Двойной шанс куплен\\!*

Ваш шанс стать пидором удвоен на *{date}*\\.
Списано: 8 койнов
Комиссия в банк: {commission} 🪙
Новый баланс: {balance} койн\\(ов\\)"""

DOUBLE_CHANCE_PURCHASE_SUCCESS_OTHER = """✅ *Двойной шанс куплен\\!*

*{buyer_username}* подарил\\(а\\) двойной шанс игроку *{target_username}* на *{date}*\\.
Списано: 8 койнов
Комиссия в банк: {commission} 🪙
Новый баланс: {balance} койн\\(ов\\)"""

DOUBLE_CHANCE_ERROR_INSUFFICIENT_FUNDS = "❌ Недостаточно средств\\! Нужно 8 койнов\\, у вас: {balance}"
DOUBLE_CHANCE_ERROR_ALREADY_BOUGHT_TODAY = "❌ Вы уже купили двойной шанс сегодня\\! Можно купить только один раз в день\\."
DOUBLE_CHANCE_ACTIVATED_IN_GAME = "🎲 <b>{username}</b> использовал(а) двойной шанс и победил(а)! Эффект израсходован."

# Сообщения для предсказаний
PREDICTION_SELECT_PLAYER = """🔮 *Выберите игрока для предсказания*

Кто\, по вашему мнению\, станет пидором дня\?

_Если угадаете \\- получите 30 койнов\\!_"""

PREDICTION_PURCHASE_SUCCESS = """✅ *Предсказание создано\\!*

*{buyer_username}* предсказал\\(а\\)\\, что *{predicted_username}* станет пидором дня *{date}*\\.
Списано: 3 койна
Комиссия в банк: {commission} 🪙
Новый баланс: {balance} койн\\(ов\\)

Результат узнаете после розыгрыша\\!"""

PREDICTION_ERROR_INSUFFICIENT_FUNDS = "❌ Недостаточно средств\\! Нужно 3 койна\\, у вас: {balance}"
PREDICTION_ERROR_ALREADY_EXISTS = "❌ Вы уже сделали предсказание на сегодня\\!"
PREDICTION_ERROR_SELF = "❌ Нельзя предсказать самого себя\\!"

PREDICTION_RESULT_CORRECT = """🎉 *Ваше предсказание сбылось\\!*

Вы правильно предсказали\, что *{predicted_username}* станет пидором дня\\.
Награда: \\+30 койнов
Новый баланс: {balance} койн\\(ов\\)"""

PREDICTION_RESULT_INCORRECT = """😔 *Ваше предсказание не сбылось*

Вы предсказали *{predicted_username}*\, но пидором дня стал\\(а\\) *{actual_username}*\\.
Удачи в следующий раз\\!"""

# Сообщения для объединённых уведомлений о предсказаниях
PREDICTIONS_SUMMARY_HEADER = """🔮 *Результаты предсказаний:*"""
PREDICTIONS_SUMMARY_CORRECT_ITEM = """✅ {username} угадал\\(а\\)\\! \\+30 🪙 \\(баланс: {balance}\\)"""
PREDICTIONS_SUMMARY_INCORRECT_ITEM = """❌ {username} не угадал\\(а\\)"""

# Сообщения для двойного шанса другому игроку
DOUBLE_CHANCE_SELECT_PLAYER = """🎲 *Выберите игрока для двойного шанса*

Кому вы хотите подарить двойной шанс\?

_Двойной шанс удваивает вероятность стать пидором дня\\._"""

# Сообщения для перевыборов
REROLL_BUTTON_TEXT = "🔄 Перевыборы (15 💰)"
REROLL_ANNOUNCEMENT = """🔄 <b>ПЕРЕВЫБОРЫ!</b>

👤 {initiator_name} заплатил(а) 15 💰 за перевыбор!
❌ Бывший пидор: {old_winner_name}
✅ Новый пидор дня: {new_winner_name}!

<code>🎉 {initiator_name}: -15 пидор-койн(ов)</code>
<code>🎉 {old_winner_name}: сохраняет свои койны</code>
<code>🎉 {new_winner_name}: +{new_winner_coins} пидор-койн(ов)</code>{protection_info}{double_chance_info}{predictions_info}"""

REROLL_ERROR_ALREADY_USED = "❌ Перевыбор уже использован сегодня"
REROLL_ERROR_INSUFFICIENT_FUNDS = "❌ Недостаточно койнов! Баланс: {balance} 💰"
REROLL_SUCCESS_NOTIFICATION = "🔄 Перевыбор запущен!"

# Сообщения для кнопки "Дайте койнов"
GIVE_COINS_BUTTON_TEXT = "💰 Дайте койнов"
GIVE_COINS_SUCCESS = "✅ Вы получили +{amount} 💰! Баланс: {balance} 💰"
GIVE_COINS_ALREADY_CLAIMED = "❌ Вы уже получали койны сегодня!"
GIVE_COINS_ERROR_NOT_REGISTERED = "❌ Вы не зарегистрированы в игре! Используйте /pidoreg"

# Сообщения для передачи койнов
TRANSFER_SELECT_PLAYER = """💸 *Выберите получателя*

Кому вы хотите передать койны\?

_Комиссия: 10% \\(минимум 1 койн\\)_
_Минимальная сумма: 2 койна_"""

TRANSFER_SELECT_AMOUNT = """💸 *Выберите сумму перевода*

👤 Получатель: {receiver_name}
💰 Ваш баланс: {balance} 💰

_Комиссия 10% пойдёт в банк чата_"""

TRANSFER_ENTER_AMOUNT = """💸 *Введите сумму перевода*

Получатель: *{receiver_name}*

Введите сумму койнов для перевода \\(минимум 2\\):

_Комиссия 10% пойдёт в банк чата_"""

TRANSFER_SUCCESS = """💸 *Перевод выполнен\\!*

👤 Отправитель: {sender_name}
👤 Получатель: {receiver_name}

📤 Отправлено: {amount_sent} 💰
📥 Получено: {amount_received} 💰
🏦 Комиссия в банк: {commission} 💰

💰 Баланс {sender_name}: {sender_balance} 💰
💰 Баланс {receiver_name}: {receiver_balance} 💰
🏦 Баланс банка: {bank_balance} 💰"""

TRANSFER_ERROR_COOLDOWN = """❌ Вы уже совершали перевод сегодня\\.
Следующий перевод будет доступен завтра\\."""

TRANSFER_ERROR_INSUFFICIENT_FUNDS = """❌ Недостаточно койнов\\!
Ваш баланс: {balance} 💰
Требуется: {amount} 💰"""

TRANSFER_ERROR_MIN_AMOUNT = "❌ Минимальная сумма перевода: 2 💰"
TRANSFER_ERROR_SELF_TRANSFER = "❌ Нельзя передавать койны себе"

# Сообщения для банка чата
BANK_INFO = """🏦 *Банк чата*

💰 Баланс: {balance} 💰

_Комиссии от переводов накапливаются здесь\\._
_В будущем банк будет использоваться для розыгрышей\\!_"""


# ============================================================================
# Функции-генераторы сообщений с динамическими ценами
# ============================================================================

def get_shop_menu(config: 'ChatConfig') -> str:
    """
    Генерирует меню магазина с актуальными ценами из конфигурации.

    Args:
        config: Конфигурация чата

    Returns:
        str: Отформатированное меню магазина
    """
    items = []

    if config.constants.immunity_enabled:
        items.append(
            f"🛡️ *Защита от пидора* \\({config.constants.immunity_price} койнов\\)\n"
            f"Защищает от выбора пидором на следующий день\\.\n"
            f"Кулдаун: {config.constants.immunity_cooldown_days} дней после использования\\."
        )

    if config.constants.double_chance_enabled:
        items.append(
            f"🎲 *Двойной шанс* \\({config.constants.double_chance_price} койнов\\)\n"
            f"Удваивает ваш шанс стать пидором дня\\.\n"
            f"Действует до следующей победы\\."
        )

    if config.constants.prediction_enabled:
        items.append(
            f"🔮 *Предсказание* \\({config.constants.prediction_price} койна\\)\n"
            f"Предскажите\\, кто станет пидором дня\\.\n"
            f"Если угадаете \\- получите {config.constants.prediction_reward} койнов\\!"
        )

    items_text = "\n\n".join(items)

    return f"""🏪 *Магазин пидор\\-койнов*

💰 Ваш баланс: *{{balance}}* койн\\(ов\\)

*Доступные товары:*

{items_text}

_Выберите товар нажатием на кнопку ниже\\._"""


def get_immunity_messages(config: 'ChatConfig') -> dict:
    """
    Генерирует сообщения о защите с актуальными ценами.

    Args:
        config: Конфигурация чата

    Returns:
        dict: Словарь с сообщениями о защите
    """
    return {
        'purchase_success': f"""✅ *Защита куплена\\!*

Вы защищены от выбора пидором *{{date}}*\\.
Списано: {config.constants.immunity_price} койнов
Комиссия в банк: {{commission}} 🪙
Новый баланс: {{balance}} койн\\(ов\\)""",

        'error_insufficient_funds': f"❌ Недостаточно средств\\! Нужно {config.constants.immunity_price} койнов\\, у вас: {{balance}}",

        'error_already_active': "❌ Защита уже активна на *{date}*\\!",

        'error_cooldown': "❌ Защита на кулдауне\\! Можно использовать снова с *{date}*",

        'item_desc': f"🛡️ Защита ({config.constants.immunity_price} койнов)"
    }


def get_double_chance_messages(config: 'ChatConfig') -> dict:
    """
    Генерирует сообщения о двойном шансе с актуальными ценами.

    Args:
        config: Конфигурация чата

    Returns:
        dict: Словарь с сообщениями о двойном шансе
    """
    return {
        'purchase_success_self': f"""✅ *Двойной шанс куплен\\!*

Ваш шанс стать пидором удвоен на *{{date}}*\\.
Списано: {config.constants.double_chance_price} койнов
Комиссия в банк: {{commission}} 🪙
Новый баланс: {{balance}} койн\\(ов\\)""",

        'purchase_success_other': f"""✅ *Двойной шанс куплен\\!*

*{{buyer_username}}* подарил\\(а\\) двойной шанс игроку *{{target_username}}* на *{{date}}*\\.
Списано: {config.constants.double_chance_price} койнов
Комиссия в банк: {{commission}} 🪙
Новый баланс: {{balance}} койн\\(ов\\)""",

        'error_insufficient_funds': f"❌ Недостаточно средств\\! Нужно {config.constants.double_chance_price} койнов\\, у вас: {{balance}}",

        'error_already_bought_today': "❌ Вы уже купили двойной шанс сегодня\\! Можно купить только один раз в день\\.",

        'item_desc': f"🎲 Двойной шанс ({config.constants.double_chance_price} койнов)"
    }


def get_prediction_messages(config: 'ChatConfig') -> dict:
    """
    Генерирует сообщения о предсказаниях с актуальными ценами.

    Args:
        config: Конфигурация чата

    Returns:
        dict: Словарь с сообщениями о предсказаниях
    """
    return {
        'select_player': f"""🔮 *Выберите игрока для предсказания*

Кто\\, по вашему мнению\\, станет пидором дня\\?

_Если угадаете \\- получите {config.constants.prediction_reward} койнов\\!_""",

        'purchase_success': f"""✅ *Предсказание создано\\!*

*{{buyer_username}}* предсказал\\(а\\)\\, что *{{predicted_username}}* станет пидором дня *{{date}}*\\.
Списано: {config.constants.prediction_price} койна
Комиссия в банк: {{commission}} 🪙
Новый баланс: {{balance}} койн\\(ов\\)

Результат узнаете после розыгрыша\\!""",

        'error_insufficient_funds': f"❌ Недостаточно средств\\! Нужно {config.constants.prediction_price} койна\\, у вас: {{balance}}",

        'error_already_exists': "❌ Вы уже сделали предсказание на сегодня\\!",

        'error_self': "❌ Нельзя предсказать самого себя\\!",

        'result_correct': f"""🎉 *Ваше предсказание сбылось\\!*

Вы правильно предсказали\\, что *{{predicted_username}}* станет пидором дня\\.
Награда: \\+{config.constants.prediction_reward} койнов
Новый баланс: {{balance}} койн\\(ов\\)""",

        'result_incorrect': """😔 *Ваше предсказание не сбылось*

Вы предсказали *{predicted_username}*\\, но пидором дня стал\\(а\\) *{actual_username}*\\.
Удачи в следующий раз\\!""",

        'item_desc': f"🔮 Предсказание ({config.constants.prediction_price} койна)"
    }


def get_reroll_messages(config: 'ChatConfig') -> dict:
    """
    Генерирует сообщения о перевыборах с актуальными ценами.

    Args:
        config: Конфигурация чата

    Returns:
        dict: Словарь с сообщениями о перевыборах
    """
    return {
        'button_text': f"🔄 Перевыборы ({config.constants.reroll_price} 💰)",

        'announcement': f"""🔄 <b>ПЕРЕВЫБОРЫ!</b>

👤 {{initiator_name}} заплатил(а) {config.constants.reroll_price} 💰 за перевыбор!
❌ Бывший пидор: {{old_winner_name}}
✅ Новый пидор дня: {{new_winner_name}}!

<code>🎉 {{initiator_name}}: -{config.constants.reroll_price} пидор-койн(ов)</code>
<code>🎉 {{old_winner_name}}: сохраняет свои койны</code>
<code>🎉 {{new_winner_name}}: +{{new_winner_coins}} пидор-койн(ов)</code>{{protection_info}}{{double_chance_info}}{{predictions_info}}""",

        'error_already_used': "❌ Перевыбор уже использован сегодня",

        'error_insufficient_funds': "❌ Недостаточно койнов! Баланс: {balance} 💰",

        'success_notification': "🔄 Перевыбор запущен!"
    }


def get_transfer_messages(config: 'ChatConfig') -> dict:
    """
    Генерирует сообщения о переводах с актуальными параметрами.

    Args:
        config: Конфигурация чата

    Returns:
        dict: Словарь с сообщениями о переводах
    """
    return {
        'select_player': f"""💸 *Выберите получателя*

Кому вы хотите передать койны\\?

_Комиссия: 10% \\(минимум 1 койн\\)_
_Минимальная сумма: {config.constants.transfer_min_amount} койна_""",

        'select_amount': """💸 *Выберите сумму перевода*

👤 Получатель: {receiver_name}
💰 Ваш баланс: {balance} 💰

_Комиссия 10% пойдёт в банк чата_""",

        'enter_amount': f"""💸 *Введите сумму перевода*

Получатель: *{{receiver_name}}*

Введите сумму койнов для перевода \\(минимум {config.constants.transfer_min_amount}\\):

_Комиссия 10% пойдёт в банк чата_""",

        'success': """💸 *Перевод выполнен\\!*

👤 Отправитель: {sender_name}
👤 Получатель: {receiver_name}

📤 Отправлено: {amount_sent} 💰
📥 Получено: {amount_received} 💰
🏦 Комиссия в банк: {commission} 💰

💰 Баланс {sender_name}: {sender_balance} 💰
💰 Баланс {receiver_name}: {receiver_balance} 💰
🏦 Баланс банка: {bank_balance} 💰""",

        'error_cooldown': """❌ Вы уже совершали перевод сегодня\\.
Следующий перевод будет доступен завтра\\.""",

        'error_insufficient_funds': """❌ Недостаточно койнов\\!
Ваш баланс: {balance} 💰
Требуется: {amount} 💰""",

        'error_min_amount': f"❌ Минимальная сумма перевода: {config.constants.transfer_min_amount} 💰",

        'error_self_transfer': "❌ Нельзя передавать койны себе"
    }


def get_rules_message(config: 'ChatConfig') -> str:
    """
    Генерирует сообщение с правилами игры с актуальными ценами.

    Args:
        config: Конфигурация чата

    Returns:
        str: Отформатированное сообщение с правилами (HTML формат)
    """
    # Вычисляем значение для self-pidor
    self_pidor_coins = config.constants.coins_per_win * config.constants.self_pidor_multiplier

    rules_parts = [
        "<b>Правила игры «Пидор Дня»</b> (только для групповых чатов):\n",
        "<b>1.</b> Зарегистрируйтесь в игру по команде /pidoreg",
        "<b>2.</b> Подождите пока зарегиструются все (или большинство :)",
        "<b>3.</b> Запустите розыгрыш по команде /pidor",
        "<b>4.</b> Просмотр статистики канала по команде /pidorstats, /pidorall",
        "<b>5.</b> Личная статистика по команде /pidorme",
        "<b>6.</b> Статистика за последний год по команде /pidor2020 (так же есть за 2016-2020)",
        "<b>7.</b> Просмотр пропущенных дней в текущем году: /pidormissed",
        "<b>8.</b> Финальное голосование за пропущенные дни (29-30 декабря): /pidorfinal",
        "<b>9.</b> Статус финального голосования: /pidorfinalstatus",
        "<b>10. (!!! Только для администраторов чатов)</b>: удалить из игры может только Админ канала, "
        "сначала выведя по команде список игроков: /pidormin list",
        "Удалить же игрока можно по команде (используйте идентификатор пользователя - цифры из списка пользователей): "
        "/pidormin del 123456\n",
        "<b>Важно</b>, розыгрыш проходит только <b>раз в день</b>, повторная команда выведет <b>результат</b> игры.\n",
        f"<b>Пидор-койны:</b> За участие в игре начисляются пидор-койны! Победитель получает {config.constants.coins_per_win} койна, "
        f"запустивший команду - {config.constants.coins_per_command} койн. Если ты сам стал пидором дня - получаешь {self_pidor_coins} койнов! "
        "Потратить койны можно в магазине: /pidorshop"
    ]

    # Добавляем информацию о товарах магазина в зависимости от feature flags
    if config.constants.immunity_enabled:
        rules_parts.append(
            f"• <b>Защита от пидора</b> ({config.constants.immunity_price} койнов) - защита на следующий день, если тебя выберут - перевыбор. Кулдаун {config.constants.immunity_cooldown_days} дней."
        )

    if config.constants.double_chance_enabled:
        rules_parts.append(
            f"• <b>Двойной шанс</b> ({config.constants.double_chance_price} койнов) - удваивает шанс стать пидором дня на следующий розыгрыш. Можно купить для любого игрока!"
        )

    if config.constants.prediction_enabled:
        rules_parts.append(
            f"• <b>Предсказание</b> ({config.constants.prediction_price} койна) - угадай пидора дня и получи {config.constants.prediction_reward} койнов!"
        )

    if config.constants.transfer_enabled:
        rules_parts.append(
            "• <b>Перевод койнов</b> - передай койны другому игроку (комиссия по ключевой ставке ЦБ РФ)."
        )

    rules_parts.append("• <b>Банк чата</b> - общий банк, куда идут комиссии с покупок и переводов.\n")

    rules_parts.append(
        "<b>Комиссия:</b> При каждой покупке в магазине и переводе койнов часть денег (по ключевой ставке ЦБ РФ) идёт в банк чата. "
        "Минимальная комиссия - 1 койн."
    )
    rules_parts.append("Баланс койнов: /pidorcoinsme, топ по койнам: /pidorcoinsstats\n")

    rules_parts.append(
        "<b>Финальное голосование:</b> В конце года (29-30 декабря) можно запустить взвешенное голосование "
        "для распределения пропущенных дней. Финальное голосование с кастомными кнопками (поддерживает любое количество участников). "
        "Результаты скрыты до завершения. Вес каждого голоса равен количеству побед игрока в текущем году. "
        f"Голосование доступно только если пропущено менее {config.constants.max_missed_days_for_final_voting} дней. Завершить голосование могут администраторы чата: /pidorfinalclose\n"
    )

    rules_parts.append("Сброс розыгрыша происходит каждый день в 12 часов ночи по Москве.\n")
    rules_parts.append('Поддержать бота можно по <a href="https://github.com/vodka-429/pidor-bot-2/">ссылке</a> :)')

    return "\n".join(rules_parts)
