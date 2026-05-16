from pathlib import Path
from config import settings
from services import process_manager
import time


def offline_stream_ok() -> bool:
    playlist = settings.offline_dir / "offline.m3u8"
    if not playlist.exists():
        return False
    # si el archivo no se actualizó en los últimos 30s, está estancado
    age = time.time() - playlist.stat().st_mtime
    return age < 30


def channel_stream_ok(channel_id: str) -> bool:
    playlist = settings.hls_dir / channel_id / f"{channel_id}.m3u8"
    if not playlist.exists():
        return False
    age = time.time() - playlist.stat().st_mtime
    return age < 30


def system_status() -> dict:
    running = process_manager.list_running()
    return {
        "offline_stream": offline_stream_ok(),
        "active_relays": len(running),
        "relay_pids": running,
    }
