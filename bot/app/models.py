from datetime import datetime
from typing import Optional, List

from sqlalchemy import UniqueConstraint, Column, BigInteger
from sqlmodel import SQLModel, Field, Relationship


class GamePlayer(SQLModel, table=True):
    game_id: Optional[int] = Field(default=None, foreign_key="game.id", primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="tguser.id", primary_key=True)

    # user: 'TGUser' = Relationship(back_populates="games")
    # game: 'Game' = Relationship(back_populates="players")
    # winner_at: List['GameResult'] = Relationship(back_populates="winner")


class TGUser(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tg_id: int = Field(sa_column=Column('tg_id', BigInteger(), nullable=False, index=True, unique=True))
    username: Optional[str]
    first_name: str
    last_name: Optional[str]
    lang_code: str = 'en'
    is_blocked: bool = False

    games: List['Game'] = Relationship(back_populates="players", link_model=GamePlayer)
    game_results: List['GameResult'] = Relationship(back_populates="winner")
    final_voting_wins: List['FinalVoting'] = Relationship(back_populates="winner")
    coin_transactions: List['PidorCoinTransaction'] = Relationship(back_populates="user")

    created_at: datetime = Field(default=datetime.utcnow(), nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow,
                                 nullable=False)
    last_seen_at: datetime = Field(default=datetime.utcnow(), nullable=False)

    def full_username(self, mention: bool = False, prefix: str = '@'):
        if self.username:
            return (prefix if mention else '') + self.username
        else:
            # Add mention handling with `[{first_name}{" "+last_name}](tg://user?id={tg_id})`
            return self.first_name + (" " + self.last_name if self.last_name else '')


class Game(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    chat_id: int = Field(sa_column=Column('chat_id', BigInteger(), nullable=False, index=True))

    players: List[TGUser] = Relationship(back_populates="games", link_model=GamePlayer)
    results: List['GameResult'] = Relationship(back_populates="game")
    final_votings: List['FinalVoting'] = Relationship(back_populates="game")
    coin_transactions: List['PidorCoinTransaction'] = Relationship(back_populates="game")


class GameResult(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")
    winner_id: int = Field(foreign_key="tguser.id")
    year: int
    day: int

    winner: TGUser = Relationship(back_populates="game_results")
    game: Game = Relationship(back_populates="results")

    __table_args__ = (
        UniqueConstraint('game_id', 'year', 'day', name='unique_game_result'),
    )


class FinalVoting(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")
    year: int
    poll_id: str
    poll_message_id: int
    started_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    ended_at: Optional[datetime] = None
    winner_id: Optional[int] = Field(default=None, foreign_key="tguser.id")
    missed_days_count: int
    missed_days_list: str  # JSON string with list of missed days
    votes_data: str = Field(default='{}')  # JSON string with votes structure: {user_id: [candidate_ids]}
    is_results_hidden: bool = Field(default=True)  # Hide results until voting ends
    voting_message_id: Optional[int] = None  # ID of the message with voting buttons
    winners_data: str = Field(default='[]')  # JSON string with list of all winners: [{"winner_id": 1, "days_count": 3}, ...]
    excluded_leaders_data: str = Field(default='[]')  # JSON string with list of excluded leaders: [{"player_id": 1, "wins": 21}, ...]

    winner: Optional[TGUser] = Relationship(back_populates="final_voting_wins")
    game: Game = Relationship(back_populates="final_votings")

    __table_args__ = (
        UniqueConstraint('game_id', 'year', name='unique_final_voting'),
    )


class TiktokLink(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    link: str = Field(index=True)
    share_link: Optional[str] = Field(default=None, index=True)
    # ID of the message with the cached video inside special channel
    telegram_message_id: str

    created_at: datetime = Field(default=datetime.utcnow(), nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow,
                                 nullable=False)


class KVItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    chat_id: int = Field(sa_column=Column(BigInteger(), nullable=False, index=True))
    key: str = Field(index=True)
    value: str

    created_at: datetime = Field(default=datetime.utcnow(), nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow,
                                 nullable=False)

    __table_args__ = (
        UniqueConstraint('chat_id', 'key', name='unique_kv_item'),
    )


class PidorCoinTransaction(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id", nullable=False)
    user_id: int = Field(foreign_key="tguser.id", nullable=False)
    amount: int = Field(nullable=False)
    year: int = Field(nullable=False)
    reason: str = Field(nullable=False)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

    game: Game = Relationship(back_populates="coin_transactions")
    user: TGUser = Relationship(back_populates="coin_transactions")


class GamePlayerEffect(SQLModel, table=True):
    """Эффекты игрока в конкретной игре (магазин пидор-койнов)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id", nullable=False)
    user_id: int = Field(foreign_key="tguser.id", nullable=False)

    # Защита от пидора (year+day)
    immunity_year: Optional[int] = Field(default=None)
    immunity_day: Optional[int] = Field(default=None)
    immunity_last_used: Optional[datetime] = Field(default=None)  # Для кулдауна

    # Двойной шанс теперь хранится в отдельной таблице DoubleChancePurchase
    # Поля double_chance_until и double_chance_bought_by УДАЛЕНЫ

    next_win_multiplier: int = Field(default=1)

    game: Game = Relationship()
    user: TGUser = Relationship()

    __table_args__ = (
        UniqueConstraint('game_id', 'user_id', name='unique_game_player_effect'),
    )


class DoubleChancePurchase(SQLModel, table=True):
    """
    Покупки двойного шанса.

    Хранит информацию о том, кто и для кого купил двойной шанс.
    Двойной шанс действует на день, указанный в year+day (следующий день после покупки).
    Один покупатель может купить только один двойной шанс в день.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id", nullable=False)
    buyer_id: int = Field(foreign_key="tguser.id", nullable=False)  # Кто купил
    target_id: int = Field(foreign_key="tguser.id", nullable=False)  # Для кого купил
    year: int = Field(nullable=False)  # Год ДЕЙСТВИЯ (не покупки!)
    day: int = Field(nullable=False)   # День ДЕЙСТВИЯ (не покупки!)
    is_used: bool = Field(default=False)  # Использован ли (после победы)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

    game: Game = Relationship()
    buyer: TGUser = Relationship(sa_relationship_kwargs={"foreign_keys": "[DoubleChancePurchase.buyer_id]"})
    target: TGUser = Relationship(sa_relationship_kwargs={"foreign_keys": "[DoubleChancePurchase.target_id]"})

    __table_args__ = (
        UniqueConstraint('game_id', 'buyer_id', 'year', 'day', name='unique_double_chance_purchase'),
    )


class Prediction(SQLModel, table=True):
    """Предсказания пидора дня (магазин пидор-койнов)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id", nullable=False)
    user_id: int = Field(foreign_key="tguser.id", nullable=False)  # Кто предсказывает
    predicted_user_id: int = Field(foreign_key="tguser.id", nullable=False)  # Кого предсказывают
    year: int = Field(nullable=False)
    day: int = Field(nullable=False)
    is_correct: Optional[bool] = Field(default=None)  # Результат предсказания (None до проверки)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

    game: Game = Relationship()
    user: TGUser = Relationship(sa_relationship_kwargs={"foreign_keys": "[Prediction.user_id]"})
    predicted_user: TGUser = Relationship(sa_relationship_kwargs={"foreign_keys": "[Prediction.predicted_user_id]"})

    __table_args__ = (
        UniqueConstraint('game_id', 'user_id', 'year', 'day', name='unique_prediction'),
    )
