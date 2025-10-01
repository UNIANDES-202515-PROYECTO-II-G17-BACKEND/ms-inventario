from fastapi import APIRouter
from config import settings
from dependencies import readiness_check

router = APIRouter()

@router.get('/health', tags=['meta'])
async def health():
    return {'status': 'ok', 'service': settings.SERVICE_NAME}

@router.get('/ready', tags=['meta'])
async def ready():
    checks = await readiness_check()
    overall = all(
        v is True or (isinstance(v, dict) and all(x is True for x in v.values()))
        for v in checks.values()
        if v is not None
    )
    return {'ready': overall, 'checks': checks}
