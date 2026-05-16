import shutil
import logging
from pathlib import Path
from config import settings
from services import process_manager

logger = logging.getLogger(__name__)


def build_hls_cmd(iptv_url: str, output_dir: Path, slug: str) -> list[str]:
    playlist = output_dir / f"{slug}.m3u8"
    return [
        settings.ffmpeg_bin,
        "-loglevel", "warning",
        "-re",
        "-i", iptv_url,
        "-c", "copy",                           # sin transcoding
        "-f", "hls",
        "-hls_time", str(settings.hls_time),
        "-hls_list_size", str(settings.hls_list_size),
        "-hls_flags", "delete_segments+append_list",
        "-hls_segment_filename", str(output_dir / f"{slug}_%05d.ts"),
        str(playlist),
    ]


def start_relay(channel_id: str, iptv_url: str) -> int:
    output_dir = settings.hls_dir / channel_id
    output_dir.mkdir(parents=True, exist_ok=True)

    log_file = settings.logs_dir / f"{channel_id}.log"
    cmd = build_hls_cmd(iptv_url, output_dir, channel_id)

    logger.info(f"[{channel_id}] iniciando relay → {iptv_url[:60]}...")
    return process_manager.start_process(channel_id, cmd, log_file)


def stop_relay(channel_id: str):
    process_manager.stop_process(channel_id)
    removed = _cleanup_segments(channel_id)
    logger.info(f"[{channel_id}] relay detenido — {removed} archivos eliminados")


def _cleanup_segments(channel_id: str) -> int:
    """Elimina directorio HLS completo del canal. Retorna cantidad de archivos eliminados."""
    output_dir = settings.hls_dir / channel_id
    if not output_dir.exists():
        return 0

    ts_count = len(list(output_dir.glob("*.ts")))
    m3u8_count = len(list(output_dir.glob("*.m3u8")))
    total = ts_count + m3u8_count

    shutil.rmtree(output_dir, ignore_errors=True)
    logger.debug(f"[{channel_id}] cleanup: {ts_count} .ts + {m3u8_count} .m3u8 eliminados")
    return total


def delete_relay_data(channel_id: str):
    """Limpieza completa al eliminar un canal: segmentos + log."""
    stop_relay(channel_id)

    log_file = settings.logs_dir / f"{channel_id}.log"
    if log_file.exists():
        log_file.unlink()
        logger.debug(f"[{channel_id}] log eliminado")


def stream_url(channel_id: str) -> str:
    return f"{settings.base_url}/streams/live/{channel_id}/{channel_id}.m3u8"
