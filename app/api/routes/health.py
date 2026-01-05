from fastapi import APIRouter
from datetime import datetime
from app.core.schemas import HealthResponse
from app.core.config import settings

router = APIRouter(tags=["health"])

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """헬스 체크"""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow(),
        version=settings.api_version
    )