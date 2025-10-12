from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from src.config import settings
from typing import Optional
from redis import Redis

engine = create_engine(settings.SQLALCHEMY_DATABASE_URI, pool_pre_ping=True)
_redis_client: Optional[Redis] = None

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

@contextmanager
def session_for_schema(schema: str):
    with engine.connect().execution_options(schema_translate_map={None: schema}) as conn:
        with conn.begin() as transaction:
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
            with SessionLocal(bind=conn) as session:
                yield session


def get_redis() -> Optional[Redis]:
    """Singleton Redis sync. Devuelve None si no está configurado."""
    global _redis_client
    if not settings.REDIS_HOST or not settings.REDIS_PORT:
        return None
    if _redis_client is None:
        _redis_client = Redis(host=settings.REDIS_HOST, port=int(settings.REDIS_PORT), decode_responses=True)
    return _redis_client