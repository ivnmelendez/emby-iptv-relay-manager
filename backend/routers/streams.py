import logging
import time
from fastapi import APIRouter, HTTPException
from models import ChannelStatus
from services import ffmpeg, m3u, process_manager
from services.offline import offline_stream_url
from config import settings
import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/channels", tags=["streams"])


@router.post("/{channel_id}/activate")
def activate_channel(channel_id: str):
    ch = db.get_channel(channel_id)
    if not ch:
        raise HTTPException(404, "Canal no encontrado")
    if not ch.iptv_url:
        raise HTTPException(400, "Canal sin URL IPTV — haz sync primero")

    # Protección race condition — lock no bloqueante por canal
    if not process_manager.try_acquire(channel_id):
        raise HTTPException(409, "Canal en proceso de cambio de estado. Intenta en un momento.")

    try:
        # Re-leer estado actualizado tras adquirir lock
        ch = db.get_channel(channel_id)

        # Idempotente: ya estaba online → retornar estado actual
        if ch.status == ChannelStatus.online and process_manager.is_running(channel_id):
            logger.debug(f"[{channel_id}] activate ignorado — ya está ONLINE")
            return ch

        # Verificar límite global
        all_channels = db.load_channels()
        active_count = sum(1 for c in all_channels.values() if c.status == ChannelStatus.online)
        if active_count >= settings.max_active_streams:
            logger.warning(
                f"[{channel_id}] activate bloqueado — límite {settings.max_active_streams} alcanzado"
            )
            raise HTTPException(
                409,
                f"Límite alcanzado: máximo {settings.max_active_streams} streams activos. "
                f"Pon uno offline antes de activar otro.",
            )

        pid = ffmpeg.start_relay(channel_id, ch.iptv_url)

        ch.status = ChannelStatus.online
        ch.stream_url = ffmpeg.stream_url(channel_id)
        ch.pid = pid
        ch.started_at = time.time()

        db.upsert_channel(ch)
        m3u.generate_m3u(db.load_channels())
        logger.info(f"[{channel_id}] ONLINE — PID={pid}")
        return ch

    finally:
        process_manager.release(channel_id)


@router.post("/{channel_id}/offline")
def set_offline(channel_id: str):
    ch = db.get_channel(channel_id)
    if not ch:
        raise HTTPException(404, "Canal no encontrado")

    if not process_manager.try_acquire(channel_id):
        raise HTTPException(409, "Canal en proceso de cambio de estado. Intenta en un momento.")

    try:
        ch = db.get_channel(channel_id)

        # Idempotente: ya estaba offline → retornar estado actual
        if ch.status == ChannelStatus.offline:
            logger.debug(f"[{channel_id}] offline ignorado — ya está OFFLINE")
            return ch

        ffmpeg.stop_relay(channel_id)

        ch.status = ChannelStatus.offline
        ch.stream_url = offline_stream_url()
        ch.pid = None
        ch.started_at = None
        # iptv_url se conserva — permite reactivar sin nuevo sync

        db.upsert_channel(ch)
        m3u.generate_m3u(db.load_channels())
        logger.info(f"[{channel_id}] OFFLINE")
        return ch

    finally:
        process_manager.release(channel_id)
