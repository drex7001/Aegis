"""Persistence adapter: SQLAlchemy models + engine (schema arrives in T4)."""

from aegis.store.engine import Base, get_engine, get_sessionmaker

__all__ = ["Base", "get_engine", "get_sessionmaker"]
