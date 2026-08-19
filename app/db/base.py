from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.core.config import settings

# DATABASE_URL normalization (postgres:// → postgresql://) is handled in
# config.py via field_validator. No double conversion needed here.
db_url = settings.DATABASE_URL

# SQLite requires check_same_thread=False for FastAPI sync + async mixing
connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}

engine = create_engine(
    db_url,
    echo=settings.DEBUG and settings.ENVIRONMENT == "development",
    connect_args=connect_args,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI database session dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
