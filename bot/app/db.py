import os

from sqlmodel import create_engine, SQLModel, Session

DATABASE_URL = os.environ.get('DATABASE_URL')

engine = create_engine(DATABASE_URL, echo=os.environ.get('DEBUG', False), pool_pre_ping=True, pool_recycle=3600)


def init_db():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
