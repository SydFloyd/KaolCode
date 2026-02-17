from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from codex_home.models import Base


def build_engine(database_url: str):
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    return create_engine(database_url, future=True, pool_pre_ping=True, connect_args=connect_args)


def build_session_factory(engine):
    return sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


def init_db(engine) -> None:
    # Avoid concurrent create_all races when orchestrator + worker start together.
    if engine.dialect.name == "postgresql":
        lock_id = 1400212026
        with engine.begin() as conn:
            conn.execute(text("SELECT pg_advisory_lock(:lock_id)"), {"lock_id": lock_id})
            try:
                Base.metadata.create_all(bind=conn)
            finally:
                conn.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": lock_id})
        return
    Base.metadata.create_all(bind=engine)


def db_session(session_factory) -> Session:
    return session_factory()
