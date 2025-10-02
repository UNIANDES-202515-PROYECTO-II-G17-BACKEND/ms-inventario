from fastapi import APIRouter
from src.config import settings

router = APIRouter()

@router.get('/health', tags=['meta'])
async def health():
    return {'status': 'ok', 'service': settings.SERVICE_NAME}