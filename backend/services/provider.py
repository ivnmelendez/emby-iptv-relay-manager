"""
Provider service.

Flujo correcto:
  refresh_cache() → descarga M3U real → provider_cache.json + groups.json
                    ÚNICO punto que toca internet.

  sync()          → lee provider_cache.json local → library.json
                    Sin internet. Seguro de ejecutar N veces.

  manage()        → promueve canal de library → channels.json + eventos.m3u
"""

from __future__ import annotations

import json
import re
import time
import logging
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

import httpx

from config import settings
from models import Channel, ChannelStatus, GroupInfo, LibraryChannel, ScanResult, SyncResult
from utils.slug import slugify
import db

logger = logging.getLogger(__name__)


@dataclass
class ProviderChannel:
    tvg_id: str
    name: str
    logo: Optional[str]
    raw_group_title: str
    url: str


@runtime_checkable
class ChannelProvider(Protocol):
    def fetch_channels(self) -> list[ProviderChannel]: ...


# ---------------------------------------------------------------------------
# Xtream Codes Provider
# ---------------------------------------------------------------------------

class XtreamCodesProvider:
    def __init__(self, host: str, username: str, password: str):
        self.host = host.rstrip("/")
        self.username = username
        self.password = password

    @property
    def m3u_url(self) -> str:
        return (
            f"{self.host}/get.php"
            f"?username={self.username}"
            f"&password={self.password}"
            f"&type=m3u_plus"
            f"&output=ts"
        )

    def fetch_channels(self) -> list[ProviderChannel]:
        logger.info(f"Descargando M3U de {self.host}...")
        with httpx.Client(timeout=60) as client:
            resp = client.get(self.m3u_url)
            resp.raise_for_status()
        return _parse_m3u(resp.text)


def _parse_m3u(content: str) -> list[ProviderChannel]:
    channels: list[ProviderChannel] = []
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF"):
            url = lines[i + 1].strip() if i + 1 < len(lines) else ""
            if url and not url.startswith("#"):
                channels.append(ProviderChannel(
                    tvg_id=_attr(line, "tvg-id"),
                    name=_attr(line, "tvg-name") or _inline_name(line),
                    logo=_attr(line, "tvg-logo") or None,
                    raw_group_title=_attr(line, "group-title"),
                    url=url,
                ))
            i += 2
        else:
            i += 1
    logger.info(f"Parseados {len(channels)} canales del proveedor")
    return channels


def _attr(line: str, attr: str) -> str:
    m = re.search(rf'{attr}="([^"]*)"', line)
    return m.group(1).strip() if m else ""


def _inline_name(line: str) -> str:
    m = re.search(r",(.+)$", line)
    return m.group(1).strip() if m else ""


def matches_filters(raw_group: str, filters: list[str]) -> bool:
    group_lower = raw_group.lower()
    return any(f.lower() in group_lower for f in filters)


def get_provider() -> XtreamCodesProvider:
    if not settings.iptv_host:
        raise ValueError("IPTV_HOST no configurado en .env")
    return XtreamCodesProvider(
        host=settings.iptv_host,
        username=settings.iptv_username,
        password=settings.iptv_password,
    )


def _channel_id(pc: ProviderChannel) -> str:
    if pc.tvg_id:
        return slugify(pc.tvg_id)
    return slugify(pc.name)


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _save_provider_cache(channels: list[ProviderChannel]) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "fetched_at": time.time(),
        "total": len(channels),
        "channels": [
            {
                "tvg_id": pc.tvg_id,
                "name": pc.name,
                "logo": pc.logo,
                "raw_group_title": pc.raw_group_title,
                "url": pc.url,
            }
            for pc in channels
        ],
    }
    settings.provider_cache_file.write_text(json.dumps(data))
    logger.info(f"Cache guardada: {len(channels)} canales → {settings.provider_cache_file}")


def _load_provider_cache() -> list[ProviderChannel]:
    """Lee cache local. No toca internet. Lanza ValueError si no existe."""
    if not settings.provider_cache_file.exists():
        raise ValueError(
            "Cache del proveedor vacía. "
            "Usa 'Refresh cache' para descargar canales del proveedor primero."
        )
    data = json.loads(settings.provider_cache_file.read_text())
    return [
        ProviderChannel(
            tvg_id=ch.get("tvg_id", ""),
            name=ch.get("name", ""),
            logo=ch.get("logo"),
            raw_group_title=ch.get("raw_group_title", ""),
            url=ch.get("url", ""),
        )
        for ch in data.get("channels", [])
    ]


def cache_info() -> dict:
    """Metadata de la cache actual. None si no existe."""
    if not settings.provider_cache_file.exists():
        return {"exists": False, "fetched_at": None, "total": 0}
    try:
        data = json.loads(settings.provider_cache_file.read_text())
        return {
            "exists": True,
            "fetched_at": data.get("fetched_at"),
            "total": data.get("total", 0),
        }
    except Exception:
        return {"exists": False, "fetched_at": None, "total": 0}


# ---------------------------------------------------------------------------
# Refresh Cache — ÚNICO punto que toca internet
# ---------------------------------------------------------------------------

def refresh_cache() -> ScanResult:
    """
    Descarga el M3U completo del proveedor → guarda provider_cache.json
    y actualiza groups.json. Esta es la ÚNICA función que hace requests
    a la IPTV. Ejecutar manualmente cuando quieras actualizar los eventos.
    """
    provider = get_provider()
    all_channels = provider.fetch_channels()

    _save_provider_cache(all_channels)

    # Actualizar groups.json desde los canales frescos
    groups_data: dict[str, dict] = {}
    for ch in all_channels:
        title = ch.raw_group_title or "Sin grupo"
        if title not in groups_data:
            groups_data[title] = {"count": 0, "names": []}
        groups_data[title]["count"] += 1
        if len(groups_data[title]["names"]) < 3:
            groups_data[title]["names"].append(ch.name)

    now = time.time()
    existing = db.load_groups()
    new_count = 0

    for title, data in groups_data.items():
        suggested = matches_filters(title, settings.group_filters)
        if title in existing:
            g = existing[title]
            g.count = data["count"]
            g.last_seen_at = now
            g.available = True
            g.channels_preview = data["names"]
            g.suggested = suggested
        else:
            existing[title] = GroupInfo(
                group_title=title,
                count=data["count"],
                selected=False,
                available=True,
                suggested=suggested,
                first_seen_at=now,
                last_seen_at=now,
                channels_preview=data["names"],
            )
            new_count += 1

    for title in list(existing.keys()):
        if title not in groups_data:
            existing[title].available = False

    db.save_groups(existing)
    suggested_count = sum(1 for g in existing.values() if g.suggested)
    logger.info(
        f"Refresh cache: {len(all_channels)} canales, {len(groups_data)} grupos, "
        f"{new_count} nuevos grupos"
    )

    return ScanResult(
        total_fetched=len(all_channels),
        total_groups=len(groups_data),
        new_groups=new_count,
        suggested_groups=suggested_count,
        unavailable_groups=0,
    )


# Alias para compatibilidad con routers que usan scan()
scan = refresh_cache


# ---------------------------------------------------------------------------
# Sync — lee cache local, cero internet
# ---------------------------------------------------------------------------

def sync() -> SyncResult:
    """
    Importa canales de la cache local → library.json.
    NO hace requests. NO toca internet. Seguro de ejecutar N veces.
    """
    from services.m3u import generate_m3u

    all_channels = _load_provider_cache()
    total_fetched = len(all_channels)

    groups = db.load_groups()
    active_titles: set[str] = {
        g.group_title for g in groups.values() if g.selected and g.available
    }
    filter_mode = "groups_selected"
    warning: Optional[str] = None

    if not active_titles:
        if not settings.group_filters:
            raise ValueError(
                "No hay grupos seleccionados. "
                "Selecciona grupos y vuelve a hacer Sync."
            )
        warning = (
            "Sin grupos seleccionados — usando GROUP_FILTERS de .env como fallback. "
            "Haz scan + select para control total."
        )
        filter_mode = "group_filters_fallback"
        logger.warning(warning)

    if filter_mode == "groups_selected":
        matched = [c for c in all_channels if c.raw_group_title in active_titles]
    else:
        matched = [c for c in all_channels if matches_filters(c.raw_group_title, settings.group_filters)]

    logger.info(
        f"Sync (local cache): {len(matched)}/{total_fetched} canales "
        f"coinciden con grupos seleccionados"
    )

    library = db.load_library()
    managed = db.load_channels()
    now = time.time()
    new_count = 0
    updated_count = 0

    for pc in matched:
        cid = _channel_id(pc)
        if not cid:
            continue

        if cid in library:
            lib_ch = library[cid]
            lib_ch.last_seen_at = now
            lib_ch.logo = pc.logo or lib_ch.logo
            lib_ch.iptv_url = pc.url
            lib_ch.managed = cid in managed
            updated_count += 1
        else:
            library[cid] = LibraryChannel(
                id=cid,
                name=pc.name,
                logo=pc.logo,
                raw_group_title=pc.raw_group_title,
                iptv_url=pc.url,
                imported_at=now,
                last_seen_at=now,
                managed=cid in managed,
            )
            new_count += 1

        if cid in managed:
            ch = managed[cid]
            ch.last_seen_at = now
            ch.logo = pc.logo or ch.logo
            if ch.status == ChannelStatus.offline:
                ch.iptv_url = pc.url
            managed[cid] = ch

    db.save_library(library)
    db.save_channels(managed)
    generate_m3u(managed)
    logger.info(f"Sync → library: {new_count} nuevos, {updated_count} actualizados")

    return SyncResult(
        total_fetched=total_fetched,
        matched=len(matched),
        new_channels=new_count,
        updated_channels=updated_count,
        filter_mode=filter_mode,
        warning=warning,
    )


# ---------------------------------------------------------------------------
# Manage — promueve canal de library a managed (aparece en Emby)
# ---------------------------------------------------------------------------

def manage_channel(channel_id: str) -> Channel:
    from services.m3u import generate_m3u

    library = db.load_library()
    if channel_id not in library:
        raise ValueError(f"Canal '{channel_id}' no encontrado en library")

    lib_ch = library[channel_id]
    managed = db.load_channels()

    if channel_id in managed:
        lib_ch.managed = True
        db.save_library(library)
        return managed[channel_id]

    ch = Channel(
        id=lib_ch.id,
        name=lib_ch.name,
        logo=lib_ch.logo,
        group=lib_ch.raw_group_title,
        raw_group_title=lib_ch.raw_group_title,
        provider_channel_name=lib_ch.name,
        iptv_url=lib_ch.iptv_url,
        status=ChannelStatus.offline,
        imported_at=lib_ch.imported_at,
        last_seen_at=lib_ch.last_seen_at,
    )

    managed[channel_id] = ch
    db.save_channels(managed)

    lib_ch.managed = True
    db.save_library(library)

    generate_m3u(managed)
    logger.info(f"[{channel_id}] agregado a managed channels")
    return ch


def unmanage_channel(channel_id: str):
    library = db.load_library()
    if channel_id in library:
        library[channel_id].managed = False
        db.save_library(library)
