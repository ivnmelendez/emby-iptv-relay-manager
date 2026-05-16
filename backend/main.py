import logging
import logging.config
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import channels, streams, system, provider, ui
from services import m3u
from models import ChannelStatus
from config import settings
import db

logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        }
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "default"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "httpx": {"level": "WARNING"},
        "uvicorn.access": {"level": "WARNING"},
    },
})

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando IPTV Relay Manager...")

    # 1. Crear directorios runtime (crítico antes de cualquier operación)
    for d in settings.runtime_dirs():
        d.mkdir(parents=True, exist_ok=True)

    # 2. Validar BASE_URL — si es inválido Emby rechazará el M3U
    if not settings.base_url_clean.startswith(("http://", "https://")):
        logger.error(
            f"BASE_URL inválido: '{settings.base_url}' "
            f"— Debe comenzar con http:// o https://"
        )
    elif "localhost" in settings.base_url or "127.0.0.1" in settings.base_url:
        logger.warning(
            f"BASE_URL apunta a localhost: '{settings.base_url}' "
            f"— Emby en otro equipo NO podrá acceder. "
            f"Cambia a la IP pública del VPS en .env"
        )
    else:
        logger.info(f"BASE_URL: {settings.base_url_clean}")

    # 3. Validar que HLS dir es escribible — detecta problemas de volúmenes Docker
    _test = settings.hls_dir / ".startup_check"
    try:
        _test.touch()
        _test.unlink()
        logger.info(
            f"Dirs OK — streams: {settings.streams_dir} | data: {settings.data_dir}"
        )
    except OSError as e:
        logger.error(
            f"HLS dir NO escribible: {settings.hls_dir} — {e}\n"
            f"  Verifica volúmenes Docker: docker compose down && docker compose up -d\n"
            f"  En VPS: el usuario del container necesita write access a ./streams/"
        )

    # 4. Resetear canales online a offline (PIDs perdidos en reinicio)
    all_channels = db.load_channels()
    reset_count = 0
    for ch in all_channels.values():
        if ch.status == ChannelStatus.online:
            ch.status = ChannelStatus.offline
            ch.pid = None
            ch.started_at = None
            reset_count += 1
    if reset_count:
        db.save_channels(all_channels)
        logger.warning(f"Startup: {reset_count} canales reseteados a OFFLINE")

    m3u.generate_m3u(all_channels)
    logger.info(f"Startup: {len(all_channels)} canales cargados, M3U generado")
    yield
    logger.info("IPTV Relay Manager detenido")


app = FastAPI(title="IPTV Relay Manager", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers — API JSON
app.include_router(channels.router)
app.include_router(streams.router)
app.include_router(system.router)
app.include_router(provider.router)

# Router — Dashboard UI (páginas + HTMX)
app.include_router(ui.router)
