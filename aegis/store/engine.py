from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from aegis.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all canonical tables (speckit spec 02)."""


def get_engine(url: str | None = None) -> Engine:
    return create_engine(url or get_settings().database_url)


def get_sessionmaker(engine: Engine | None = None) -> sessionmaker:
    return sessionmaker(bind=engine or get_engine())
