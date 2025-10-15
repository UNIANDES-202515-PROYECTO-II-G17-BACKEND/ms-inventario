from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
import logging, sys

from .domain import models
from sqlalchemy import inspect
from src.infrastructure.infrastructure import engine
from .routes.health import router as health_router
from .routes.inventario import router as inventario_router

log = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

KNOWN_SCHEMAS = ["co","ec","mx","pe"]  # o desde ENV

@asynccontextmanager
async def lifespan(app):
    for schema in KNOWN_SCHEMAS:
        try:
            eng = engine.execution_options(schema_translate_map={None: schema})
            models.Base.metadata.create_all(bind=eng)
            inspector = inspect(eng)
            tables = inspector.get_table_names(schema=schema)
            log.info(f"✅ {len(tables)} tablas creadas/verificadas en schema '{schema}': {tables}")
        except Exception as e:
            log.error(f"❌ Error creando tablas en schema {schema}: {e}")
    yield
    log.info("🛑 Finalizando aplicación ms-inventario")

app = FastAPI(
    title=settings.SERVICE_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(inventario_router)
