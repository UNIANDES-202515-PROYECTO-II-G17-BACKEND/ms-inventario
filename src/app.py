from fastapi import FastAPI
from config import settings
from routes.health import router as health_router
from dependencies import lifespan

app = FastAPI(
    title=settings.SERVICE_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
)

app.include_router(health_router)
