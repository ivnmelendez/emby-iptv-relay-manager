from fastapi import APIRouter
from services.health import system_status

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/health")
def health():
    return system_status()
