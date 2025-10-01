from contextlib import asynccontextmanager
from typing import Dict, Optional

from redis.asyncio import from_url as redis_from_url
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine, async_sessionmaker
from sqlalchemy import text
from google.cloud import pubsub_v1, bigquery, bigtable, storage

from config import settings

# Global clients/engines
redis_client = None
db_engines: Dict[str, AsyncEngine] = {}        # country_code -> engine
db_sessions: Dict[str, async_sessionmaker] = {}# country_code -> sessionmaker
pub_client: Optional[pubsub_v1.PublisherClient] = None
bq_client: Optional[bigquery.Client] = None
bt_client: Optional[bigtable.Client] = None
gcs_client: Optional[storage.Client] = None

COUNTRIES = ("CO", "MX", "EC", "PE")

def _dsn_for_country(cc: str) -> Optional[str]:
    cc = cc.upper()
    if cc == "CO": return settings.DATABASE_URL_CO
    if cc == "MX": return settings.DATABASE_URL_MX
    if cc == "EC": return settings.DATABASE_URL_EC
    if cc == "PE": return settings.DATABASE_URL_PE
    return None

def get_db_session(country_code: str) -> async_sessionmaker:
    # Return a sessionmaker bound to the shard for country_code.
    cc = country_code.upper()
    if cc not in db_sessions:
        dsn = _dsn_for_country(cc)
        if not dsn:
            raise ValueError(f"No DATABASE_URL configured for shard {cc}")
        engine = create_async_engine(dsn, pool_pre_ping=True)
        db_engines[cc] = engine
        db_sessions[cc] = async_sessionmaker(engine, expire_on_commit=False)
    return db_sessions[cc]

async def readiness_check() -> dict:
    # Performs lightweight checks against configured backends.
    status = {"redis": None, "db": {}, "pubsub": None, "bigquery": None, "bigtable": None, "gcs": None}

    # Redis
    if settings.REDIS_URL:
        try:
            global redis_client
            if redis_client is None:
                redis_client = redis_from_url(settings.REDIS_URL, decode_responses=True)
            pong = await redis_client.ping()
            status["redis"] = bool(pong)
        except Exception as e:
            status["redis"] = f"error: {e!s}"

    # Databases (try simple SELECT 1)
    for cc in COUNTRIES:
        dsn = _dsn_for_country(cc)
        if not dsn:
            continue
        try:
            sm = get_db_session(cc)
            async with sm() as s:
                await s.execute(text("SELECT 1"))
            status["db"][cc] = True
        except Exception as e:
            status["db"][cc] = f"error: {e!s}"

    # Pub/Sub (create topic path only; no network call)
    try:
        global pub_client
        if pub_client is None:
            pub_client = pubsub_v1.PublisherClient()
        if settings.PUBSUB_TOPIC:
            _ = pub_client.topic_path(settings.GCP_PROJECT, settings.PUBSUB_TOPIC)
        status["pubsub"] = True
    except Exception as e:
        status["pubsub"] = f"error: {e!s}"

    # BigQuery
    try:
        global bq_client
        if bq_client is None:
            bq_client = bigquery.Client(project=settings.GCP_PROJECT)
        _ = settings.BQ_DATASET  # presence is enough; client init success indicates ADC ok
        status["bigquery"] = True
    except Exception as e:
        status["bigquery"] = f"error: {e!s}"

    # Bigtable
    try:
        global bt_client
        if bt_client is None:
            bt_client = bigtable.Client(project=settings.GCP_PROJECT, admin=False)
        status["bigtable"] = True
    except Exception as e:
        status["bigtable"] = f"error: {e!s}"

    # GCS
    try:
        global gcs_client
        if gcs_client is None:
            gcs_client = storage.Client(project=settings.GCP_PROJECT)
        status["gcs"] = True
    except Exception as e:
        status["gcs"] = f"error: {e!s}"

    return status

@asynccontextmanager
async def lifespan(app):
    try:
        yield
    finally:
        # Cierre ordenado
        if redis_client:
            await redis_client.close()
        for eng in db_engines.values():
            await eng.dispose()
        # Pub/Sub / BigQuery / Bigtable / GCS usan conexiones administradas por cliente
