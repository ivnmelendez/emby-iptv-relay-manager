import subprocess
import signal
import os
import threading
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# channel_id → proceso FFmpeg activo
_processes: dict[str, subprocess.Popen] = {}

# Locks por canal — previenen race conditions en activate/offline simultáneos
_channel_locks: dict[str, threading.Lock] = {}
_locks_mutex = threading.Lock()


def _get_lock(channel_id: str) -> threading.Lock:
    with _locks_mutex:
        if channel_id not in _channel_locks:
            _channel_locks[channel_id] = threading.Lock()
        return _channel_locks[channel_id]


def try_acquire(channel_id: str) -> bool:
    """Intenta adquirir el lock del canal. Retorna False si ya está en uso."""
    acquired = _get_lock(channel_id).acquire(blocking=False)
    if not acquired:
        logger.warning(f"[{channel_id}] lock ocupado — operación simultánea bloqueada")
    return acquired


def release(channel_id: str):
    lock = _channel_locks.get(channel_id)
    if lock:
        try:
            lock.release()
        except RuntimeError:
            pass  # ya liberado


def start_process(channel_id: str, cmd: list[str], log_file: Path) -> int:
    stop_process(channel_id)  # cleanup previo si existe

    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "a") as lf:
        proc = subprocess.Popen(
            cmd,
            stdout=lf,
            stderr=lf,
            start_new_session=True,
        )

    _processes[channel_id] = proc
    logger.info(f"[{channel_id}] FFmpeg iniciado — PID={proc.pid}")
    return proc.pid


def stop_process(channel_id: str) -> bool:
    proc = _processes.pop(channel_id, None)
    if proc is None:
        return False

    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=5)
        logger.info(f"[{channel_id}] FFmpeg terminado — PID={proc.pid}")
    except ProcessLookupError:
        logger.debug(f"[{channel_id}] proceso ya no existía")
    except Exception as e:
        logger.warning(f"[{channel_id}] SIGTERM falló ({e}), forzando SIGKILL")
        try:
            proc.kill()
        except Exception:
            pass

    return True


def is_running(channel_id: str) -> bool:
    proc = _processes.get(channel_id)
    return proc is not None and proc.poll() is None


def get_pid(channel_id: str) -> Optional[int]:
    proc = _processes.get(channel_id)
    if proc and proc.poll() is None:
        return proc.pid
    return None


def list_running() -> dict[str, int]:
    return {
        cid: proc.pid
        for cid, proc in _processes.items()
        if proc.poll() is None
    }
