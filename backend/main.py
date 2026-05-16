import logging
import logging.config
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from routers import channels, streams, system, provider, ui
from services import m3u
from models import ChannelStatus
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
    logger.info(f"Startup: {len(all_channels)} canales cargados")
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
