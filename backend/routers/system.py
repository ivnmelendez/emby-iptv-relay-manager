import os
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from services.health import system_status
from config import settings

router = APIRouter(prefix="/api/system", tags=["system"])

_VALID_SCHEMES = ("http://", "https://")


@router.get("/health")
def health():
    status = system_status()
    hls = settings.hls_dir
    offline = settings.offline_dir

    # Estado de dirs y volúmenes
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

    # Estado de BASE_URL
    base = settings.base_url_clean
    status["base_url"] = {
        "value": base,
        "valid_scheme": base.startswith(_VALID_SCHEMES),
        "is_localhost": "localhost" in base or "127.0.0.1" in base,
        "offline_stream_url": settings.offline_stream_url,
    }

    return status


@router.get("/playlist")
def debug_playlist():
    """
    Debug: muestra el contenido exacto de eventos.m3u.
    Permite verificar URLs absolutas, BASE_URL y formato.
    Útil para diagnosticar errores de Emby 'Invalid URI'.
    """
    if not settings.m3u_file.exists():
        return {
            "error": "eventos.m3u no existe",
            "path": str(settings.m3u_file),
            "hint": "Haz sync de canales primero",
        }

    content = settings.m3u_file.read_text()
    lines = content.splitlines()

    # Extraer URLs del M3U (líneas que no empiezan con #)
    urls = [l.strip() for l in lines if l.strip() and not l.startswith("#")]
    invalid = [u for u in urls if not u.startswith(_VALID_SCHEMES)]
    localhost_urls = [u for u in urls if "localhost" in u or "127.0.0.1" in u]

    return {
        "base_url": settings.base_url_clean,
        "base_url_valid": settings.base_url_clean.startswith(_VALID_SCHEMES),
        "base_url_localhost": "localhost" in settings.base_url_clean,
        "m3u_path": str(settings.m3u_file),
        "total_channels": len(urls),
        "invalid_urls": invalid[:10],
        "localhost_urls": localhost_urls[:5],
        "sample_urls": urls[:5],
        "warnings": (
            ["BASE_URL inválido — no empieza con http://"]
            if not settings.base_url_clean.startswith(_VALID_SCHEMES)
            else []
        ) + (
            ["BASE_URL es localhost — Emby en otro equipo no puede acceder"]
            if "localhost" in settings.base_url_clean
            else []
        ) + (
            [f"{len(invalid)} URLs malformadas en el M3U"]
            if invalid
            else []
        ),
    }


@router.get("/playlist/raw", response_class=PlainTextResponse)
def playlist_raw():
    """Devuelve el contenido crudo de eventos.m3u — para copiar/verificar directamente."""
    if not settings.m3u_file.exists():
        return "# eventos.m3u no existe — haz sync primero"
    return settings.m3u_file.read_text()
