import os
from fastapi import APIRouter
from services.health import system_status
from config import settings

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/health")
def health():
    status = system_status()

    # Estado de directorios y volúmenes — útil para debuggear mounts Docker
    hls = settings.hls_dir
    offline = settings.offline_dir
    status["dirs"] = {
        "streams_root": str(settings.streams_dir),
        "hls": str(hls),
        "hls_exists": hls.exists(),
        "hls_writable": hls.exists() and os.access(hls, os.W_OK),
        "offline": str(offline),
        "offline_exists": offline.exists(),
        "data": str(settings.data_dir),
        "data_writable": settings.data_dir.exists() and os.access(settings.data_dir, os.W_OK),
    }
    return status
