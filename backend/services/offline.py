from config import settings


def offline_stream_url() -> str:
    """URL pública del stream offline (la que usa Emby para canales OFFLINE)."""
    return settings.offline_stream_url
