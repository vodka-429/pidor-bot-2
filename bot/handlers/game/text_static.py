REGISTRATION_SUCCESS = """*OK\!* Ты теперь участвуешь в игре "*Пидор Дня*"\!"""
REGISTRATION_MANY_SUCCESS = """*OK\!* {username} теперь участвует в игре "*Пидор Дня*"\!"""
ERROR_ALREADY_REGISTERED = """Эй\, ты уже в игре\!"""
ERROR_ALREADY_REGISTERED_MANY = """Эй\, {username} уже в игре\!"""
REMOVE_REGISTRATION = """*OK\!* Ты больше *не* участвуешь в игре "*Пидор Дня*"\!\n_P\.S\. Но всё равно пидор\!_"""
REMOVE_REGISTRATION_ERROR = """Ээээ\, тьфу\, ты и так не зарегестрирован\!"""
PLAYER_REMOVE_SUCCESS = """✅ Удалено {count} игрок\(ов\)\: {usernames}"""
PLAYER_REMOVE_NONE = """✅ Все игроки в чате\, удалять некого\."""
PLAYER_REMOVE_NOT_ADMIN = """❌ Только администратор чата может удалять игроков\."""
CURRENT_DAY_GAME_RESULT = """Согласно моей информации, по результатам сегодняшнего розыгрыша *пидор дня* \- {username}\!"""
STATS_ALL_TIME = """Топ\-50 *пидоров* за все время:\n\n{player_stats}\nВсего участников — {player_count}"""
STATS_CURRENT_YEAR = """Топ\-50 *пидоров* за текущий год\:\n\n{player_stats}\nВсего участников — {player_count}"""
STATS_LIST_ITEM = """*{number}\.* {username} — {amount} раз\\(а\\)\n"""
STATS_LIST_ITEM_INACTIVE = """*{number}\.* {username} _\\(вышел, пидор\\)_ — {amount} раз\\(а\\)\n"""
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

# Сообщения для достижений
ACHIEVEMENT_EARNED_TEMPLATE = "🏆 Достижение! {name}: +{reward} 💰"
ACHIEVEMENTS_EARNED_HEADER = "\n\n🎖️ Новые достижения:"

# Сообщения для просмотра достижений
ACHIEVEMENTS_HEADER = "🎖️ *Достижения {user_name}:*"
ACHIEVEMENT_EARNED_FORMAT = "✅ {name} — {date}"
ACHIEVEMENT_NOT_EARNED_FORMAT = "⬜ {name}"
ACHIEVEMENTS_TOTAL_COINS = "\n\n💰 *Всего заработано:* {total} койнов"
ACHIEVEMENTS_EMPTY = "У вас пока нет достижений\\. Играйте\\, чтобы получить их\\!"


# Сообщения для магазина пидор-койнов
SHOP_ERROR_NOT_YOUR_SHOP = "❌ Это не твой магазин! Открой свой командой /pidorshop"

# Сообщения для кнопки "Дайте койнов"
GIVE_COINS_BUTTON_TEXT = "💰 Дайте койнов"
GIVE_COINS_SUCCESS = "✅ Вы получили +{amount} 💰! Баланс: {balance} 💰"
GIVE_COINS_ALREADY_CLAIMED = "❌ Вы уже получали койны сегодня!"
GIVE_COINS_ERROR_NOT_REGISTERED = "❌ Вы не зарегистрированы в игре! Используйте /pidoreg"

# Сообщения для банка чата
BANK_INFO = """🏦 *Банк чата*

💰 Баланс: {balance} 💰

_Комиссии от переводов накапливаются здесь\\._
_В будущем банк будет использоваться для розыгрышей\\!_"""


# ============================================================================
# Функции-генераторы сообщений с динамическими ценами из конфигурации
# ============================================================================

def get_shop_menu(config) -> str:
    """
    Генерирует меню магазина с актуальными ценами из конфигурации.

    Args:
        config: ChatConfig с константами для конкретного чата

    Returns:
        str: Форматированное меню магазина
    """
    from bot.handlers.game.config import ChatConfig

    if not isinstance(config, ChatConfig):
        raise TypeError(f"Expected ChatConfig, got {type(config)}")

    c = config.constants

    return f"""🏪 *Магазин пидор\\-койнов*

💰 Ваш баланс: *{{balance}}* койн\\(ов\\)

*Доступные товары:*

🛡️ *Защита от пидора* \\({c.immunity_price} койнов\\)
Защищает от выбора пидором на следующий день\\.
Кулдаун: {c.immunity_cooldown_days} дней после использования\\.

🎲 *Двойной шанс* \\({c.double_chance_price} койнов\\)
Удваивает ваш шанс стать пидором дня\\.
Действует до следующей победы\\.

🔮 *Предсказание* \\({c.prediction_price} койна\\)
Предскажите\, кто станет пидором дня\\.
Если угадаете \\- получите {c.prediction_reward} койнов\\!

_Выберите товар нажатием на кнопку ниже\\._"""


def get_immunity_messages(config) -> dict:
    """
    Генерирует сообщения о защите с актуальными ценами из конфигурации.

    Args:
        config: ChatConfig с константами для конкретного чата

    Returns:
        dict: Словарь с сообщениями о защите
    """
    from bot.handlers.game.config import ChatConfig

    if not isinstance(config, ChatConfig):
        raise TypeError(f"Expected ChatConfig, got {type(config)}")

    c = config.constants

    return {
        'item_desc': f"🛡️ Защита ({c.immunity_price} койнов)",
        'purchase_success': f"""✅ *Защита куплена\\!*

Вы защищены от выбора пидором *{{date}}*\\.
Списано: {c.immunity_price} койнов
Комиссия в банк: {{commission}} 🪙
Новый баланс: {{balance}} койн\\(ов\\)""",
        'error_insufficient_funds': f"❌ Недостаточно средств\\! Нужно {c.immunity_price} койнов\\, у вас: {{balance}}",
        'error_already_active': "❌ Защита уже активна на *{date}*\\!",
        'error_cooldown': "❌ Защита на кулдауне\\! Можно использовать снова с *{date}*",
        'activated_in_game': "🛡️ <b>{username}</b> был(а) защищён(а) от выбора! Перевыбираем...\n\n<code>🎉 {username_plain}: +{amount} пидор-койн(ов) за спасение</code>"
    }


def get_double_chance_messages(config) -> dict:
    """
    Генерирует сообщения о двойном шансе с актуальными ценами из конфигурации.

    Args:
        config: ChatConfig с константами для конкретного чата

    Returns:
        dict: Словарь с сообщениями о двойном шансе
    """
    from bot.handlers.game.config import ChatConfig

    if not isinstance(config, ChatConfig):
        raise TypeError(f"Expected ChatConfig, got {type(config)}")

    c = config.constants

    return {
        'item_desc': f"🎲 Двойной шанс ({c.double_chance_price} койнов)",
        'purchase_success_self': f"""✅ *Двойной шанс куплен\\!*

Ваш шанс стать пидором удвоен на *{{date}}*\\.
Списано: {c.double_chance_price} койнов
Комиссия в банк: {{commission}} 🪙
Новый баланс: {{balance}} койн\\(ов\\)""",
        'purchase_success_other': f"""✅ *Двойной шанс куплен\\!*

*{{buyer_username}}* подарил\\(а\\) двойной шанс игроку *{{target_username}}* на *{{date}}*\\.
Списано: {c.double_chance_price} койнов
Комиссия в банк: {{commission}} 🪙
Новый баланс: {{balance}} койн\\(ов\\)""",
        'error_insufficient_funds': f"❌ Недостаточно средств\\! Нужно {c.double_chance_price} койнов\\, у вас: {{balance}}",
        'error_already_bought_today': "❌ Вы уже купили двойной шанс сегодня\\! Можно купить только один раз в день\\.",
        'activated_in_game': "🎲 <b>{username}</b> использовал(а) двойной шанс и победил(а)! Эффект израсходован.",
        'select_player': """🎲 *Выберите игрока для двойного шанса*

Кому вы хотите подарить двойной шанс\?

_Двойной шанс удваивает вероятность стать пидором дня\\._"""
    }


def get_prediction_messages(config) -> dict:
    """
    Генерирует сообщения о предсказаниях с актуальными ценами из конфигурации.

    Args:
        config: ChatConfig с константами для конкретного чата

    Returns:
        dict: Словарь с сообщениями о предсказаниях
    """
    from bot.handlers.game.config import ChatConfig

    if not isinstance(config, ChatConfig):
        raise TypeError(f"Expected ChatConfig, got {type(config)}")

    c = config.constants

    return {
        'item_desc': f"🔮 Предсказание ({c.prediction_price} койна)",
        'select_player': f"""🔮 *Выберите игрока для предсказания*

Кто\, по вашему мнению\, станет пидором дня\?

_Если угадаете \\- получите {c.prediction_reward} койнов\\!_""",
        'purchase_success': f"""✅ *Предсказание создано\\!*

*{{buyer_username}}* предсказал\\(а\\)\\, что *{{predicted_username}}* станет пидором дня *{{date}}*\\.
Списано: {c.prediction_price} койна
Комиссия в банк: {{commission}} 🪙
Новый баланс: {{balance}} койн\\(ов\\)

Результат узнаете после розыгрыша\\!""",
        'error_insufficient_funds': f"❌ Недостаточно средств\\! Нужно {c.prediction_price} койна\\, у вас: {{balance}}",
        'error_already_exists': "❌ Вы уже сделали предсказание на сегодня\\!",
        'error_self': "❌ Нельзя предсказать самого себя\\!",
        'result_correct': f"""🎉 *Ваше предсказание сбылось\\!*

Вы правильно предсказали\, что *{{predicted_username}}* станет пидором дня\\.
Награда: \\+{c.prediction_reward} койнов
Новый баланс: {{balance}} койн\\(ов\\)""",
        'result_incorrect': """😔 *Ваше предсказание не сбылось*

Вы предсказали *{predicted_username}*\, но пидором дня стал\\(а\\) *{actual_username}*\\.
Удачи в следующий раз\\!""",
        'summary_header': """🔮 *Результаты предсказаний:*""",
        'summary_correct_item': f"""✅ {{username}} угадал\\(а\\)\\! \\+{c.prediction_reward} 🪙 \\(баланс: {{balance}}\\)""",
        'summary_incorrect_item': """❌ {username} не угадал\\(а\\)"""
    }


def get_reroll_messages(config) -> dict:
    """
    Генерирует сообщения о перевыборах с актуальными ценами из конфигурации.

    Args:
        config: ChatConfig с константами для конкретного чата

    Returns:
        dict: Словарь с сообщениями о перевыборах
    """
    from bot.handlers.game.config import ChatConfig

    if not isinstance(config, ChatConfig):
        raise TypeError(f"Expected ChatConfig, got {type(config)}")

    c = config.constants

    return {
        'button_text': f"🔄 Перевыборы ({c.reroll_price} 💰)",
        'announcement': f"""🔄 <b>ПЕРЕВЫБОРЫ!</b>

👤 {{initiator_name}} заплатил(а) {c.reroll_price} 💰 за перевыбор!
❌ Бывший пидор: {{old_winner_name}}
✅ Новый пидор дня: {{new_winner_name}}!

<code>🎉 {{initiator_name}}: -{c.reroll_price} пидор-койн(ов)</code>
<code>🎉 {{old_winner_name}}: сохраняет свои койны</code>
<code>🎉 {{new_winner_name}}: +{{new_winner_coins}} пидор-койн(ов)</code>{{protection_info}}{{double_chance_info}}{{predictions_info}}""",
        'error_already_used': "❌ Перевыбор уже использован сегодня",
        'error_insufficient_funds': f"❌ Недостаточно койнов! Баланс: {{balance}} 💰",
        'success_notification': "🔄 Перевыбор запущен!"
    }


def get_transfer_messages(config) -> dict:
    """
    Генерирует сообщения о переводах с актуальными параметрами из конфигурации.

    Args:
        config: ChatConfig с константами для конкретного чата

    Returns:
        dict: Словарь с сообщениями о переводах
    """
    from bot.handlers.game.config import ChatConfig

    if not isinstance(config, ChatConfig):
        raise TypeError(f"Expected ChatConfig, got {type(config)}")

    c = config.constants

    return {
        'select_player': f"""💸 *Выберите получателя*

Кому вы хотите передать койны\?

_Комиссия: 10% \\(минимум 1 койн\\)_
_Минимальная сумма: {c.transfer_min_amount} койна_""",
        'select_amount': """💸 *Выберите сумму перевода*

👤 Получатель: {receiver_name}
💰 Ваш баланс: {balance} 💰

_Комиссия 10% пойдёт в банк чата_""",
        'enter_amount': f"""💸 *Введите сумму перевода*

Получатель: *{{receiver_name}}*

Введите сумму койнов для перевода \\(минимум {c.transfer_min_amount}\\):

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
        'error_min_amount': f"❌ Минимальная сумма перевода: {c.transfer_min_amount} 💰",
        'error_self_transfer': "❌ Нельзя передавать койны себе"
    }


def get_toast_messages(config) -> dict:
    """
    Генерирует сообщения о тостах с актуальными параметрами из конфигурации.

    Args:
        config: ChatConfig с константами для конкретного чата

    Returns:
        dict: Словарь с сообщениями о тостах
    """
    from bot.handlers.game.config import ChatConfig

    if not isinstance(config, ChatConfig):
        raise TypeError(f"Expected ChatConfig, got {type(config)}")

    c = config.constants

    return {
        'select_player': f"""🍻 *Выберите получателя тоста*

За кого вы хотите поднять тост\?

_Стоимость: {c.toast_price} койнов_
_Комиссия по ставке ЦБ РФ идёт в банк чата_""",
        'success': """🍻 *Тост поднят\\!*

👤 От: {sender_name}
👤 За: {receiver_name}

📤 Списано: {amount_sent} 💰
📥 Получено: {amount_received} 💰
🏦 Комиссия в банк: {commission} 💰

💰 Баланс {sender_name}: {sender_balance} 💰
💰 Баланс {receiver_name}: {receiver_balance} 💰""",
        'error_insufficient_funds': f"❌ Недостаточно койнов\\! Нужно {c.toast_price} 💰, а у вас: {{balance}} 💰",
    }


TOTALIZATOR_BET_PLACED = "✅ Ставка принята! Поставил(а) {stake} 🪙 за «{option}»"
TOTALIZATOR_ALREADY_BET = "❌ Ты уже поставил(а) на этот тотализатор!"
TOTALIZATOR_CLOSED = "❌ Тотализатор уже завершён."
TOTALIZATOR_DEADLINE_PASSED = "❌ Дедлайн прошёл — ставки больше не принимаются."
TOTALIZATOR_NOT_ENOUGH_COINS = "❌ Недостаточно монет! Нужно {stake} 🪙, у тебя {balance} 🪙."
TOTALIZATOR_NOT_REGISTERED = "❌ Ты не зарегистрирован(а) в игре."
TOTALIZATOR_RESOLVED_WIN = (
    "🏆 Тотализатор завершён!\n\n"
    "Победила сторона «{option}»\n"
    "Каждый победитель получает <b>{per_winner}</b> 🪙"
)
TOTALIZATOR_CANCELLED = (
    "❌ Тотализатор отменён.\n"
    "Каждый получает обратно {effective} 🪙 "
    "(комиссия {commission} 🪙 с каждой ставки ушла в банк)."
)
TOTALIZATOR_REFUNDED = (
    "♻️ Все поставили на одну сторону — ставки возвращены.\n"
    "Каждый получает {effective} 🪙 (комиссия {commission} 🪙 ушла в банк)."
)
TOTALIZATOR_CREATE_PROMPT = (
    "🎰 Отправьте параметры тотализатора одним сообщением:\n"
    "<code>&lt;ставка&gt; &lt;ДД.ММ.ГГГГ&gt; &lt;описание&gt;</code>\n\n"
    "Пример:\n<code>15 30.06.2026 Спор с Олей в тимсе</code>"
)
TOTALIZATOR_CREATE_LIMIT_PLAYER = "❌ У тебя уже есть открытый тотализатор. Сначала завершите его."
TOTALIZATOR_CREATE_LIMIT_CHAT = "❌ В чате уже 3 открытых тотализатора. Дождитесь завершения."
TOTALIZATOR_CREATE_BAD_FORMAT = (
    "❌ Неверный формат. Отправьте:\n"
    "<code>&lt;ставка&gt; &lt;ДД.ММ.ГГГГ&gt; &lt;описание&gt;</code>"
)
TOTALIZATOR_CREATE_BAD_STAKE = "❌ Ставка должна быть целым числом ≥ 1."
TOTALIZATOR_CREATE_BAD_DATE = "❌ Неверная дата. Используйте формат ДД.ММ.ГГГГ (например 30.06.2026)."
TOTALIZATOR_CREATE_DATE_PAST = "❌ Дедлайн должен быть в будущем."


def get_rules_message(config) -> str:
    """
    Генерирует сообщение с правилами игры с актуальными ценами из конфигурации.

    Args:
        config: ChatConfig с константами для конкретного чата

    Returns:
        str: Форматированное сообщение с правилами
    """
    from bot.handlers.game.config import ChatConfig
    from bot.handlers.game.achievement_constants import ACHIEVEMENTS

    if not isinstance(config, ChatConfig):
        raise TypeError(f"Expected ChatConfig, got {type(config)}")

    c = config.constants

    # Формируем список достижений из констант
    achievements_list = []
    for code, achievement in ACHIEVEMENTS.items():
        name = achievement['name']
        description = achievement['description']
        reward = achievement['reward']
        achievements_list.append(f"• {name} \\- {description} \\(\\+{reward} 💰\\)")

    achievements_text = "\n".join(achievements_list)

    return f"""📜 *Правила игры "Пидор Дня"*

🎮 *Основные правила:*
• Каждый день выбирается один пидор дня
• За победу начисляется {c.coins_per_win} пидор\\-койн\\(ов\\)
• За запуск команды /pidor начисляется {c.coins_per_command} пидор\\-койн
• Если сам себя выбрал \\- получаешь {c.coins_per_win * c.self_pidor_multiplier} пидор\\-койна

💰 *Магазин \\(/pidorshop\\):*
• 🛡️ Защита от пидора \\- {c.immunity_price} койнов
  Защищает от выбора на следующий день
  Кулдаун: {c.immunity_cooldown_days} дней

• 🎲 Двойной шанс \\- {c.double_chance_price} койнов
  Удваивает шанс стать пидором
  Действует до победы

• 🔮 Предсказание \\- {c.prediction_price} койна
  Угадай пидора дня
  Награда: {c.prediction_reward} койнов

🔄 *Перевыборы:*
• Стоимость: {c.reroll_price} койнов
• Можно использовать один раз в день
• Таймаут кнопки: {c.reroll_timeout_minutes} минут

💸 *Переводы \\(/pidortransfer\\):*
• Минимальная сумма: {c.transfer_min_amount} койна
• Комиссия: 10% в банк чата
• Один перевод в день

🍻 *Тост \\(/pidorshop → Тост\\):*
• Стоимость: {c.toast_price} койнов
• Комиссия по ставке ЦБ РФ идёт в банк чата
• Без ограничений на количество в день
• Можно поднять тост за себя

🎁 *Бесплатные койны:*
• Кнопка "Дайте койнов" под результатом
• Обычные игроки: {c.give_coins_amount} койн
• Победитель дня: {c.give_coins_winner_amount} койна
• Один раз в день

🎖️ *Достижения:*
{achievements_text}
• Просмотр достижений: /pidorshop → "🎖️ Мои достижения"

📊 *Команды:*
• /pidor \\- запустить розыгрыш
• /pidoreg \\- регистрация
• /pidorstats \\- статистика
• /pidorcoins \\- баланс койнов
• /pidorshop \\- магазин
• /pidortransfer \\- перевод койнов
• /pidorrules \\- эти правила

_Удачи в игре\\! Или не удачи\\.\\.\\. 🎲_"""
