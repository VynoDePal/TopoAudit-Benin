from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(settings.database_url, pool_pre_ping=True)


def get_db() -> Generator[Session, None, None]:
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    db = session_local()
    try:
        yield db
    finally:
        db.close()
