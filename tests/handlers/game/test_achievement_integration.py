"""Integration tests for achievements system."""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock

from bot.handlers.game.commands import pidor_cmd
from bot.handlers.game.config import GameConstants
from bot.app.models import GameResult, UserAchievement


@pytest.mark.asyncio
@pytest.mark.integration
async def test_first_blood_awarded_on_first_win(mock_update, mock_context, mock_game, sample_players, mocker):
    """Интеграционный тест выдачи достижения 'Первая кровь' при первой победе."""
    # Setup
    mock_game.players = sample_players
    mock_context.game = mock_game

    # Mock query chain
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game

    mock_missed_query = MagicMock()
    mock_missed_query.filter_by.return_value = mock_missed_query
    mock_missed_query.order_by.return_value = mock_missed_query
    mock_missed_query.first.return_value = None

    mock_result_query = MagicMock()
    mock_result_query.filter_by.return_value = mock_result_query
    mock_result_query.one_or_none.return_value = None

    mock_context.db_session.query.side_effect = [mock_game_query, mock_missed_query, mock_result_query]

    # Mock datetime
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 6
    mock_dt.day = 15
    mock_dt.timetuple.return_value.tm_yday = 167
    mock_dt.date.return_value = MagicMock()
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)

    # Mock random.choice to select winner
    winner = sample_players[0]
    mocker.patch('bot.handlers.game.commands.random.choice', side_effect=[
        winner,
        "Stage 1", "Stage 2", "Stage 3", "Stage 4: {username}",
    ])

    # Mock asyncio.sleep
    mocker.patch('bot.handlers.game.commands.asyncio.sleep', new_callable=AsyncMock)

    # Mock get_or_create_player_effects
    mocker.patch('bot.handlers.game.game_effects_service.get_or_create_player_effects',
                 return_value=MagicMock(immunity_year=None, immunity_day=None))

    # Mock exec для предсказаний и достижений
    def mock_exec_side_effect(stmt):
        mock_result = MagicMock()
        stmt_str = str(stmt).lower()

        if 'prediction' in stmt_str:
            # Нет предсказаний
            mock_result.all.return_value = []
        elif 'userachievement' in stmt_str:
            # Нет достижений (первая победа)
            mock_result.first.return_value = None
            mock_result.all.return_value = []
        elif 'gameresult' in stmt_str:
            # Это первая победа пользователя
            mock_result.all.return_value = [MagicMock()]  # Одна победа
        else:
            mock_result.all.return_value = []
            mock_result.first.return_value = None

        return mock_result

    mock_context.db_session.exec.side_effect = mock_exec_side_effect

    # Mock add_coins в обоих местах
    mock_add_coins_commands = mocker.patch('bot.handlers.game.commands.add_coins')
    mock_add_coins_achievement = mocker.patch('bot.handlers.game.achievement_service.add_coins')
    mocker.patch('bot.handlers.game.commands.get_balance', return_value=10)

    # Mock get_config_by_game_id для обоих сервисов
    mock_config = MagicMock()
    mock_config.constants = GameConstants()
    mock_config.constants.achievements_enabled = True
    mocker.patch('bot.handlers.game.achievement_service.get_config_by_game_id', return_value=mock_config)
    mocker.patch('bot.handlers.game.prediction_service.get_config_by_game_id', return_value=mock_config)

    # Mock send_result_with_reroll_button
    mocker.patch('bot.handlers.game.commands.send_result_with_reroll_button', new_callable=AsyncMock)

    # Execute
    await pidor_cmd(mock_update, mock_context)

    # Verify achievement was added to database
    add_calls = [call for call in mock_context.db_session.add.call_args_list]
    achievement_added = False
    for call in add_calls:
        if len(call[0]) > 0 and isinstance(call[0][0], UserAchievement):
            achievement = call[0][0]
            if achievement.achievement_code == "first_blood":
                achievement_added = True
                assert achievement.user_id == winner.id
                assert achievement.game_id == mock_game.id
                assert achievement.year == 2024
                break

    assert achievement_added, "First blood achievement should be added to database"

    # Verify coins were awarded for achievement (10 coins for first_blood)
    # Проверяем вызовы в achievement_service
    achievement_coin_call = None
    for call in mock_add_coins_achievement.call_args_list:
        if len(call[0]) > 5 and call[0][5] == "achievement_first_blood":
            achievement_coin_call = call
            break

    assert achievement_coin_call is not None, "Coins should be awarded for first blood achievement"
    assert achievement_coin_call[0][3] == 10, "Should award 10 coins for first blood"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_streak_achievements_awarded_correctly(mock_update, mock_context, mock_game, sample_players, mocker):
    """Интеграционный тест выдачи достижений за серии побед."""
    # Setup
    mock_game.players = sample_players
    mock_context.game = mock_game
    winner = sample_players[0]

    # Mock query chain
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game

    mock_missed_query = MagicMock()
    mock_missed_query.filter_by.return_value = mock_missed_query
    mock_missed_query.order_by.return_value = mock_missed_query
    mock_missed_query.first.return_value = None

    mock_result_query = MagicMock()
    mock_result_query.filter_by.return_value = mock_result_query
    mock_result_query.one_or_none.return_value = None

    mock_context.db_session.query.side_effect = [mock_game_query, mock_missed_query, mock_result_query]

    # Mock datetime
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 6
    mock_dt.day = 15
    mock_dt.timetuple.return_value.tm_yday = 167
    mock_dt.date.return_value = MagicMock()
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)

    # Mock random.choice
    mocker.patch('bot.handlers.game.commands.random.choice', side_effect=[
        winner,
        "Stage 1", "Stage 2", "Stage 3", "Stage 4: {username}",
    ])

    # Mock asyncio.sleep
    mocker.patch('bot.handlers.game.commands.asyncio.sleep', new_callable=AsyncMock)

    # Mock get_or_create_player_effects
    mocker.patch('bot.handlers.game.game_effects_service.get_or_create_player_effects',
                 return_value=MagicMock(immunity_year=None, immunity_day=None))

    # Create mock game results for 3-win streak
    mock_results = [
        GameResult(game_id=mock_game.id, winner_id=winner.id, year=2024, day=167),  # Today
        GameResult(game_id=mock_game.id, winner_id=winner.id, year=2024, day=166),  # Yesterday
        GameResult(game_id=mock_game.id, winner_id=winner.id, year=2024, day=165),  # Day before
    ]

    # Mock exec для предсказаний и достижений
    def mock_exec_side_effect(stmt):
        mock_result = MagicMock()
        stmt_str = str(stmt).lower()

        if 'prediction' in stmt_str:
            mock_result.all.return_value = []
        elif 'userachievement' in stmt_str:
            # Нет достижений за серии
            mock_result.first.return_value = None
            mock_result.all.return_value = []
        elif 'gameresult' in stmt_str:
            # Возвращаем серию из 3 побед
            mock_result.all.return_value = mock_results
        else:
            mock_result.all.return_value = []
            mock_result.first.return_value = None

        return mock_result

    mock_context.db_session.exec.side_effect = mock_exec_side_effect

    # Mock add_coins в обоих местах
    mock_add_coins_commands = mocker.patch('bot.handlers.game.commands.add_coins')
    mock_add_coins_achievement = mocker.patch('bot.handlers.game.achievement_service.add_coins')
    mocker.patch('bot.handlers.game.commands.get_balance', return_value=10)

    # Mock get_config_by_game_id для обоих сервисов
    mock_config = MagicMock()
    mock_config.constants = GameConstants()
    mock_config.constants.achievements_enabled = True
    mocker.patch('bot.handlers.game.achievement_service.get_config_by_game_id', return_value=mock_config)
    mocker.patch('bot.handlers.game.prediction_service.get_config_by_game_id', return_value=mock_config)

    # Mock send_result_with_reroll_button
    mocker.patch('bot.handlers.game.commands.send_result_with_reroll_button', new_callable=AsyncMock)

    # Execute
    await pidor_cmd(mock_update, mock_context)

    # Verify streak_3 achievement was added
    add_calls = [call for call in mock_context.db_session.add.call_args_list]
    streak_3_added = False
    for call in add_calls:
        if len(call[0]) > 0 and isinstance(call[0][0], UserAchievement):
            achievement = call[0][0]
            if achievement.achievement_code == "streak_3":
                streak_3_added = True
                assert achievement.user_id == winner.id
                assert achievement.game_id == mock_game.id
                break

    assert streak_3_added, "Streak 3 achievement should be added"

    # Verify coins were awarded for streak_3 (20 coins)
    # Проверяем вызовы в achievement_service
    streak_coin_call = None
    for call in mock_add_coins_achievement.call_args_list:
        if len(call[0]) > 5 and call[0][5] == "achievement_streak_3":
            streak_coin_call = call
            break

    assert streak_coin_call is not None, "Coins should be awarded for streak_3"
    assert streak_coin_call[0][3] == 20, "Should award 20 coins for streak_3"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_achievements_isolated_by_game(mock_update, mock_context, sample_players, mocker):
    """Проверка изоляции достижений по играм."""
    from bot.app.models import Game

    # Create two different games
    game1 = Game(id=1, chat_id=100)
    game1.players = sample_players
    game1.results = MagicMock()
    game1.results.append = MagicMock()

    game2 = Game(id=2, chat_id=200)
    game2.players = sample_players
    game2.results = MagicMock()
    game2.results.append = MagicMock()

    winner = sample_players[0]

    # Mock datetime
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 6
    mock_dt.day = 15
    mock_dt.timetuple.return_value.tm_yday = 167
    mock_dt.date.return_value = MagicMock()
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)

    # Mock random.choice
    mocker.patch('bot.handlers.game.commands.random.choice', side_effect=[
        winner, "Stage 1", "Stage 2", "Stage 3", "Stage 4: {username}",
        winner, "Stage 1", "Stage 2", "Stage 3", "Stage 4: {username}",
    ])

    # Mock asyncio.sleep
    mocker.patch('bot.handlers.game.commands.asyncio.sleep', new_callable=AsyncMock)

    # Mock get_or_create_player_effects
    mocker.patch('bot.handlers.game.game_effects_service.get_or_create_player_effects',
                 return_value=MagicMock(immunity_year=None, immunity_day=None))

    mocker.patch('bot.handlers.game.commands.add_coins')
    mocker.patch('bot.handlers.game.commands.get_balance', return_value=10)

    # Mock send_result_with_reroll_button
    mocker.patch('bot.handlers.game.commands.send_result_with_reroll_button', new_callable=AsyncMock)

    # Test game1 - first win, should get first_blood
    mock_context.game = game1

    mock_game_query1 = MagicMock()
    mock_game_query1.filter_by.return_value = mock_game_query1
    mock_game_query1.one_or_none.return_value = game1

    mock_missed_query1 = MagicMock()
    mock_missed_query1.filter_by.return_value = mock_missed_query1
    mock_missed_query1.order_by.return_value = mock_missed_query1
    mock_missed_query1.first.return_value = None

    mock_result_query1 = MagicMock()
    mock_result_query1.filter_by.return_value = mock_result_query1
    mock_result_query1.one_or_none.return_value = None

    mock_context.db_session.query.side_effect = [mock_game_query1, mock_missed_query1, mock_result_query1]

    # Mock exec для game1
    def mock_exec_game1(stmt):
        mock_result = MagicMock()
        stmt_str = str(stmt).lower()

        if 'prediction' in stmt_str:
            mock_result.all.return_value = []
        elif 'userachievement' in stmt_str:
            # Проверяем game_id в запросе
            if 'game_id' in stmt_str and '1' in stmt_str:
                # Нет достижений в game1
                mock_result.first.return_value = None
                mock_result.all.return_value = []
            else:
                mock_result.first.return_value = None
                mock_result.all.return_value = []
        elif 'gameresult' in stmt_str:
            # Первая победа в game1
            mock_result.all.return_value = [MagicMock()]
        else:
            mock_result.all.return_value = []
            mock_result.first.return_value = None

        return mock_result

    mock_context.db_session.exec.side_effect = mock_exec_game1

    # Mock get_config_by_game_id для обоих сервисов
    mock_config = MagicMock()
    mock_config.constants = GameConstants()
    mock_config.constants.achievements_enabled = True
    mocker.patch('bot.handlers.game.achievement_service.get_config_by_game_id', return_value=mock_config)
    mocker.patch('bot.handlers.game.prediction_service.get_config_by_game_id', return_value=mock_config)

    # Execute for game1
    await pidor_cmd(mock_update, mock_context)

    # Verify first_blood was added for game1
    game1_achievements = []
    for call in mock_context.db_session.add.call_args_list:
        if len(call[0]) > 0 and isinstance(call[0][0], UserAchievement):
            achievement = call[0][0]
            if achievement.game_id == game1.id:
                game1_achievements.append(achievement)

    assert len(game1_achievements) > 0, "Should have achievements in game1"
    assert any(a.achievement_code == "first_blood" for a in game1_achievements), \
        "Should have first_blood in game1"

    # Reset mocks for game2
    mock_context.db_session.add.reset_mock()
    mock_context.game = game2

    mock_game_query2 = MagicMock()
    mock_game_query2.filter_by.return_value = mock_game_query2
    mock_game_query2.one_or_none.return_value = game2

    mock_missed_query2 = MagicMock()
    mock_missed_query2.filter_by.return_value = mock_missed_query2
    mock_missed_query2.order_by.return_value = mock_missed_query2
    mock_missed_query2.first.return_value = None

    mock_result_query2 = MagicMock()
    mock_result_query2.filter_by.return_value = mock_result_query2
    mock_result_query2.one_or_none.return_value = None

    mock_context.db_session.query.side_effect = [mock_game_query2, mock_missed_query2, mock_result_query2]

    # Mock exec для game2 - также первая победа
    def mock_exec_game2(stmt):
        mock_result = MagicMock()
        stmt_str = str(stmt).lower()

        if 'prediction' in stmt_str:
            mock_result.all.return_value = []
        elif 'userachievement' in stmt_str:
            # Нет достижений в game2 (независимо от game1)
            mock_result.first.return_value = None
            mock_result.all.return_value = []
        elif 'gameresult' in stmt_str:
            # Первая победа в game2
            mock_result.all.return_value = [MagicMock()]
        else:
            mock_result.all.return_value = []
            mock_result.first.return_value = None

        return mock_result

    mock_context.db_session.exec.side_effect = mock_exec_game2

    # Execute for game2
    await pidor_cmd(mock_update, mock_context)

    # Verify first_blood was also added for game2 (independent from game1)
    game2_achievements = []
    for call in mock_context.db_session.add.call_args_list:
        if len(call[0]) > 0 and isinstance(call[0][0], UserAchievement):
            achievement = call[0][0]
            if achievement.game_id == game2.id:
                game2_achievements.append(achievement)

    assert len(game2_achievements) > 0, "Should have achievements in game2"
    assert any(a.achievement_code == "first_blood" for a in game2_achievements), \
        "Should have first_blood in game2 (independent from game1)"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_achievement_coins_added_to_balance(mock_update, mock_context, mock_game, sample_players, mocker):
    """Проверка начисления койнов за достижения."""
    # Setup
    mock_game.players = sample_players
    mock_context.game = mock_game
    winner = sample_players[0]

    # Mock query chain
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game

    mock_missed_query = MagicMock()
    mock_missed_query.filter_by.return_value = mock_missed_query
    mock_missed_query.order_by.return_value = mock_missed_query
    mock_missed_query.first.return_value = None

    mock_result_query = MagicMock()
    mock_result_query.filter_by.return_value = mock_result_query
    mock_result_query.one_or_none.return_value = None

    mock_context.db_session.query.side_effect = [mock_game_query, mock_missed_query, mock_result_query]

    # Mock datetime
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 6
    mock_dt.day = 15
    mock_dt.timetuple.return_value.tm_yday = 167
    mock_dt.date.return_value = MagicMock()
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)

    # Mock random.choice
    mocker.patch('bot.handlers.game.commands.random.choice', side_effect=[
        winner,
        "Stage 1", "Stage 2", "Stage 3", "Stage 4: {username}",
    ])

    # Mock asyncio.sleep
    mocker.patch('bot.handlers.game.commands.asyncio.sleep', new_callable=AsyncMock)

    # Mock get_or_create_player_effects
    mocker.patch('bot.handlers.game.game_effects_service.get_or_create_player_effects',
                 return_value=MagicMock(immunity_year=None, immunity_day=None))

    # Mock exec
    def mock_exec_side_effect(stmt):
        mock_result = MagicMock()
        stmt_str = str(stmt).lower()

        if 'prediction' in stmt_str:
            mock_result.all.return_value = []
        elif 'userachievement' in stmt_str:
            mock_result.first.return_value = None
            mock_result.all.return_value = []
        elif 'gameresult' in stmt_str:
            # Первая победа
            mock_result.all.return_value = [MagicMock()]
        else:
            mock_result.all.return_value = []
            mock_result.first.return_value = None

        return mock_result

    mock_context.db_session.exec.side_effect = mock_exec_side_effect

    # Mock add_coins to track calls в обоих местах
    mock_add_coins_commands = mocker.patch('bot.handlers.game.commands.add_coins')
    mock_add_coins_achievement = mocker.patch('bot.handlers.game.achievement_service.add_coins')
    mocker.patch('bot.handlers.game.commands.get_balance', return_value=10)

    # Mock get_config_by_game_id для обоих сервисов
    mock_config = MagicMock()
    mock_config.constants = GameConstants()
    mock_config.constants.achievements_enabled = True
    mocker.patch('bot.handlers.game.achievement_service.get_config_by_game_id', return_value=mock_config)
    mocker.patch('bot.handlers.game.prediction_service.get_config_by_game_id', return_value=mock_config)

    # Mock send_result_with_reroll_button
    mocker.patch('bot.handlers.game.commands.send_result_with_reroll_button', new_callable=AsyncMock)

    # Execute
    await pidor_cmd(mock_update, mock_context)

    # Verify coins were added for achievement (проверяем в achievement_service)
    achievement_coin_calls = [
        call for call in mock_add_coins_achievement.call_args_list
        if len(call[0]) > 5 and 'achievement_' in call[0][5]
    ]

    assert len(achievement_coin_calls) > 0, "Should have coin transactions for achievements"

    # Verify first_blood coins (10 coins)
    first_blood_call = None
    for call in achievement_coin_calls:
        if call[0][5] == "achievement_first_blood":
            first_blood_call = call
            break

    assert first_blood_call is not None, "Should have coins for first_blood"
    assert first_blood_call[0][2] == winner.id, "Coins should be for winner"
    assert first_blood_call[0][3] == 10, "Should award 10 coins for first_blood"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_achievements_disabled_no_awards(mock_update, mock_context, mock_game, sample_players, mocker):
    """Проверка что достижения не выдаются при отключённом флаге."""
    # Setup
    mock_game.players = sample_players
    mock_context.game = mock_game
    winner = sample_players[0]

    # Mock query chain
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game

    mock_missed_query = MagicMock()
    mock_missed_query.filter_by.return_value = mock_missed_query
    mock_missed_query.order_by.return_value = mock_missed_query
    mock_missed_query.first.return_value = None

    mock_result_query = MagicMock()
    mock_result_query.filter_by.return_value = mock_result_query
    mock_result_query.one_or_none.return_value = None

    mock_context.db_session.query.side_effect = [mock_game_query, mock_missed_query, mock_result_query]

    # Mock datetime
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 6
    mock_dt.day = 15
    mock_dt.timetuple.return_value.tm_yday = 167
    mock_dt.date.return_value = MagicMock()
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)

    # Mock random.choice
    mocker.patch('bot.handlers.game.commands.random.choice', side_effect=[
        winner,
        "Stage 1", "Stage 2", "Stage 3", "Stage 4: {username}",
    ])

    # Mock asyncio.sleep
    mocker.patch('bot.handlers.game.commands.asyncio.sleep', new_callable=AsyncMock)

    # Mock get_or_create_player_effects
    mocker.patch('bot.handlers.game.game_effects_service.get_or_create_player_effects',
                 return_value=MagicMock(immunity_year=None, immunity_day=None))

    # Mock exec
    def mock_exec_side_effect(stmt):
        mock_result = MagicMock()
        stmt_str = str(stmt).lower()

        if 'prediction' in stmt_str:
            mock_result.all.return_value = []
        elif 'gameresult' in stmt_str:
            # Первая победа
            mock_result.all.return_value = [MagicMock()]
        else:
            mock_result.all.return_value = []
            mock_result.first.return_value = None

        return mock_result

    mock_context.db_session.exec.side_effect = mock_exec_side_effect

    # Mock add_coins в обоих местах
    mock_add_coins_commands = mocker.patch('bot.handlers.game.commands.add_coins')
    mock_add_coins_achievement = mocker.patch('bot.handlers.game.achievement_service.add_coins')
    mocker.patch('bot.handlers.game.commands.get_balance', return_value=10)

    # Mock get_config_by_game_id with achievements DISABLED для обоих сервисов
    mock_config = MagicMock()
    mock_config.constants = GameConstants()
    mock_config.constants.achievements_enabled = False  # DISABLED!
    mocker.patch('bot.handlers.game.achievement_service.get_config_by_game_id', return_value=mock_config)
    mocker.patch('bot.handlers.game.prediction_service.get_config_by_game_id', return_value=mock_config)

    # Mock send_result_with_reroll_button
    mocker.patch('bot.handlers.game.commands.send_result_with_reroll_button', new_callable=AsyncMock)

    # Execute
    await pidor_cmd(mock_update, mock_context)

    # Verify NO achievements were added
    achievement_adds = [
        call for call in mock_context.db_session.add.call_args_list
        if len(call[0]) > 0 and isinstance(call[0][0], UserAchievement)
    ]

    assert len(achievement_adds) == 0, "No achievements should be added when disabled"

    # Verify NO achievement coins were awarded (проверяем в achievement_service)
    achievement_coin_calls = [
        call for call in mock_add_coins_achievement.call_args_list
        if len(call[0]) > 5 and 'achievement_' in call[0][5]
    ]

    assert len(achievement_coin_calls) == 0, "No achievement coins should be awarded when disabled"
