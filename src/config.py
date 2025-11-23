import os
from datetime import timedelta


class Settings:

    SERVICE_NAME = os.getenv("SERVICE_NAME", "ms-inventario")
    VERSION = os.getenv("VERSION", "0.1.0")
    REGION = os.getenv("REGION", "us-central1")

    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASS", "postgres")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "5432"))
    DB_NAME = os.getenv("DB_NAME", "db_ms_inventario")

    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = os.getenv("REDIS_PORT", "6379")

    SQLALCHEMY_DATABASE_URI = (
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )

    DEFAULT_SCHEMA = os.getenv("DEFAULT_SCHEMA", "co")
    COUNTRY_HEADER = os.getenv("COUNTRY_HEADER", "X-Country")
    GATEWAY_BASE_URL = os.getenv("GATEWAY_BASE_URL", "https://medisupply-gw-5k2l9pfv.uc.gateway.dev")

    TOPIC_PEDIDOS = os.getenv("TOPIC_PEDIDOS")
    TOPIC_INVENTARIO = os.getenv("TOPIC_INVENTARIO")
    TOPIC_LOGISTICA = os.getenv("TOPIC_LOGISTICA")
    TOPIC_VENTAS_CRM = os.getenv("TOPIC_VENTAS_CRM")
    TOPIC_TELEMETRIA = os.getenv("TOPIC_TELEMETRIA")

settings = Settings()
