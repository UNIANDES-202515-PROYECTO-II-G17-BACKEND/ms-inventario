from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from src.config import settings
from typing import Optional
from google.cloud import pubsub_v1
from redis import Redis

import json

engine = create_engine(settings.SQLALCHEMY_DATABASE_URI, pool_pre_ping=True)
_redis_client: Optional[Redis] = None
_publisher: Optional[pubsub_v1.PublisherClient] = None

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


def get_publisher() -> pubsub_v1.PublisherClient:
    """
    Devuelve un PublisherClient singleton, inicializado de forma lazy.
    Esto evita que se creen credenciales en import time (útil para tests).
    """
    global _publisher
    if _publisher is None:
        _publisher = pubsub_v1.PublisherClient()
    return _publisher


def publish_event(data: dict, topic_path: str) -> None:
    """
    Publica un evento en Pub/Sub.

    :param data: dict serializable a JSON
    :param topic_path: 'projects/.../topics/...'
    """
    payload = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
    get_publisher().publish(topic_path, payload)