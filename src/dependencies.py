from fastapi import Header
from src.config import settings
from src.infrastructure.infrastructure import session_for_schema


def get_session(X_Country: str | None = Header(default=None, alias=settings.COUNTRY_HEADER)):
    schema = (X_Country or settings.DEFAULT_SCHEMA).strip().lower()
    with session_for_schema(schema) as session:
        yield session