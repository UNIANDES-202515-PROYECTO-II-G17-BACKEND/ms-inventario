from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from src.config import settings

engine = create_engine(settings.SQLALCHEMY_DATABASE_URI, pool_pre_ping=True)

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
