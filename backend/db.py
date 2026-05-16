import json
from pathlib import Path
from typing import Dict
from models import Channel, GroupInfo
from config import settings


def _ensure_dirs():
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    settings.hls_dir.mkdir(parents=True, exist_ok=True)
    settings.offline_dir.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------

def load_channels() -> Dict[str, Channel]:
    _ensure_dirs()
    if not settings.channels_file.exists():
        return {}
    data = json.loads(settings.channels_file.read_text())
    return {k: Channel(**v) for k, v in data.items()}


def save_channels(channels: Dict[str, Channel]):
    _ensure_dirs()
    data = {k: v.model_dump() for k, v in channels.items()}
    settings.channels_file.write_text(json.dumps(data, indent=2))


def get_channel(channel_id: str) -> Channel | None:
    return load_channels().get(channel_id)


def upsert_channel(channel: Channel):
    channels = load_channels()
    channels[channel.id] = channel
    save_channels(channels)


def delete_channel(channel_id: str) -> bool:
    channels = load_channels()
    if channel_id not in channels:
        return False
    del channels[channel_id]
    save_channels(channels)
    return True


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

def load_groups() -> Dict[str, GroupInfo]:
    _ensure_dirs()
    if not settings.groups_file.exists():
        return {}
    data = json.loads(settings.groups_file.read_text())
    return {k: GroupInfo(**v) for k, v in data.items()}


def save_groups(groups: Dict[str, GroupInfo]):
    _ensure_dirs()
    data = {k: v.model_dump() for k, v in groups.items()}
    settings.groups_file.write_text(json.dumps(data, indent=2))
