from fastapi import FastAPI
from config import settings
from routes.health import router as health_router

app = FastAPI(
    title=settings.SERVICE_NAME,
    version=settings.VERSION
)

app.include_router(health_router)
