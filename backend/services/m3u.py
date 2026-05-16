import logging
from config import settings
from models import Channel, ChannelStatus
from typing import Dict

logger = logging.getLogger(__name__)

_VALID_SCHEMES = ("http://", "https://")


def _validate_url(url: str, channel_id: str) -> str:
    """Advierte si la URL no es absoluta. Emby rechaza URLs relativas o malformadas."""
    if not url.startswith(_VALID_SCHEMES):
        logger.warning(
            f"URL inválida en eventos.m3u [{channel_id}]: '{url}' "
            f"— BASE_URL actual: '{settings.base_url}' "
            f"— Debe ser http(s)://HOST:PUERTO"
        )
    return url


def generate_m3u(channels: Dict[str, Channel]):
    base_ok = settings.base_url_clean.startswith(_VALID_SCHEMES)
    if not base_ok:
        logger.error(
            f"BASE_URL inválido: '{settings.base_url}' "
            f"— Las URLs del M3U serán inválidas para Emby. "
            f"Corrige BASE_URL en .env → BASE_URL=http://TU_IP:8080"
        )

    lines = ["#EXTM3U"]
    for ch in channels.values():
        group = ch.raw_group_title or ch.group or "Eventos"
        logo = ch.logo or ""

        stream_url = (
            ch.stream_url
            if ch.status == ChannelStatus.online and ch.stream_url
            else settings.offline_stream_url
        )

        _validate_url(stream_url, ch.id)

        lines.append(
            f'#EXTINF:-1 tvg-id="{ch.id}" tvg-name="{ch.name}" '
            f'tvg-logo="{logo}" group-title="{group}",{ch.name}'
        )
        lines.append(stream_url)

    settings.m3u_file.parent.mkdir(parents=True, exist_ok=True)
    settings.m3u_file.write_text("\n".join(lines) + "\n")

    # Loggear muestra para diagnóstico
    if channels:
        first_url = lines[2] if len(lines) > 2 else "?"
        logger.info(
            f"M3U generado: {len(channels)} canales | "
            f"base: {settings.base_url_clean} | "
            f"sample: {first_url[:80]}"
        )
