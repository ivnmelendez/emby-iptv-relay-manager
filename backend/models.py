from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
import time


class ChannelStatus(str, Enum):
    online = "online"
    offline = "offline"


class Channel(BaseModel):
    id: str                                      # slug estable (tvg-id o nombre)
    name: str
    logo: Optional[str] = None
    group: Optional[str] = None                  # grupo usado en M3U

    # metadata original del proveedor
    raw_group_title: Optional[str] = None
    provider_channel_name: Optional[str] = None

    iptv_url: Optional[str] = None               # URL del proveedor (persiste aunque offline)
    status: ChannelStatus = ChannelStatus.offline
    stream_url: str = ""                         # URL HLS pública (lo que ve Emby)
    pid: Optional[int] = None
    imported_at: Optional[float] = None
    last_seen_at: Optional[float] = None
    started_at: Optional[float] = None


class ChannelUpdate(BaseModel):
    name: Optional[str] = None
    logo: Optional[str] = None
    group: Optional[str] = None


class GroupInfo(BaseModel):
    group_title: str
    count: int
    selected: bool = False
    available: bool = True                       # false si no apareció en último scan
    suggested: bool = False                      # match con GROUP_FILTERS de .env
    first_seen_at: float = Field(default_factory=time.time)
    last_seen_at: float = Field(default_factory=time.time)
    channels_preview: list[str] = []             # primeros 3 nombres de canales (sin logos/URLs)


class GroupSelection(BaseModel):
    groups: list[str]                            # group_title strings a seleccionar


class ScanResult(BaseModel):
    total_fetched: int
    total_groups: int
    new_groups: int
    suggested_groups: int                        # grupos que matchean GROUP_FILTERS
    unavailable_groups: int                      # grupos que desaparecieron en este scan


class SyncResult(BaseModel):
    total_fetched: int
    matched: int
    new_channels: int
    updated_channels: int
    filter_mode: str                             # "groups_selected" | "group_filters_fallback"
    warning: Optional[str] = None
