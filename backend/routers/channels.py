import logging
from fastapi import APIRouter, HTTPException
from models import ChannelUpdate
from services import m3u
from services.ffmpeg import delete_relay_data
from services.provider import unmanage_channel
import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/channels", tags=["channels"])


@router.get("/")
def list_channels():
    return list(db.load_channels().values())


@router.get("/{channel_id}")
def get_channel(channel_id: str):
    ch = db.get_channel(channel_id)
    if not ch:
        raise HTTPException(404, "Canal no encontrado")
    return ch


@router.patch("/{channel_id}")
def update_channel(channel_id: str, payload: ChannelUpdate):
    ch = db.get_channel(channel_id)
    if not ch:
        raise HTTPException(404, "Canal no encontrado")
    updated = ch.model_copy(update=payload.model_dump(exclude_none=True))
    db.upsert_channel(updated)
    m3u.generate_m3u(db.load_channels())
    logger.info(f"[{channel_id}] metadata actualizada")
    return updated


@router.delete("/{channel_id}", status_code=204)
def delete_channel(channel_id: str):
    ch = db.get_channel(channel_id)
    if not ch:
        raise HTTPException(404, "Canal no encontrado")
    delete_relay_data(channel_id)
    db.delete_channel(channel_id)
    unmanage_channel(channel_id)   # actualizar flag en library
    m3u.generate_m3u(db.load_channels())
    logger.info(f"[{channel_id}] eliminado de managed channels")
