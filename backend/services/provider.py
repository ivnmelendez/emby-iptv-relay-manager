"""
Provider service — desacoplado desde el inicio.

Interfaz: ChannelProvider (Protocol)
Implementación actual: XtreamCodesProvider

Para agregar un nuevo proveedor en el futuro:
  1. Implementar ChannelProvider
  2. Actualizar get_provider()
"""

from __future__ import annotations

import re
import time
import logging
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

import httpx

from config import settings
from models import Channel, ChannelStatus, GroupInfo, ScanResult, SyncResult
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
# Scan — descubre grupos sin importar canales
# ---------------------------------------------------------------------------

def scan() -> ScanResult:
    """
    Descarga M3U completa, extrae todos los group-titles con conteos y preview.
    NO importa canales. Actualiza groups.json preservando selected.
    """
    provider = get_provider()
    all_channels = provider.fetch_channels()

    # Agregar por grupo: count + primeros 3 nombres
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
    unavailable_count = 0

    # Actualizar / crear grupos
    for title, data in groups_data.items():
        suggested = matches_filters(title, settings.group_filters)
        if title in existing:
            g = existing[title]
            g.count = data["count"]
            g.last_seen_at = now
            g.available = True
            g.channels_preview = data["names"]
            g.suggested = suggested
            # selected: NUNCA se toca automáticamente
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

    # Marcar como unavailable los que desaparecieron (sin tocar selected)
    for title in list(existing.keys()):
        if title not in groups_data:
            if existing[title].available:
                unavailable_count += 1
            existing[title].available = False

    db.save_groups(existing)

    suggested_count = sum(1 for g in existing.values() if g.suggested)
    logger.info(
        f"Scan: {len(all_channels)} canales, {len(groups_data)} grupos, "
        f"{new_count} nuevos, {unavailable_count} no disponibles"
    )

    return ScanResult(
        total_fetched=len(all_channels),
        total_groups=len(groups_data),
        new_groups=new_count,
        suggested_groups=suggested_count,
        unavailable_groups=unavailable_count,
    )


# ---------------------------------------------------------------------------
# Sync — importa canales de grupos seleccionados
# ---------------------------------------------------------------------------

def sync() -> SyncResult:
    from services.m3u import generate_m3u

    # Determinar grupos activos
    groups = db.load_groups()
    active_titles: set[str] = {
        g.group_title for g in groups.values() if g.selected and g.available
    }
    filter_mode = "groups_selected"
    warning: Optional[str] = None

    if not active_titles:
        # Fallback a GROUP_FILTERS si no hay selección explícita
        if not settings.group_filters:
            raise ValueError(
                "No hay grupos seleccionados. "
                "Haz POST /api/provider/scan y selecciona grupos con POST /api/provider/groups/select"
            )
        warning = (
            "Sin grupos seleccionados — usando GROUP_FILTERS de .env como fallback. "
            "Haz scan+select para control total."
        )
        filter_mode = "group_filters_fallback"
        logger.warning(warning)

    provider = get_provider()
    all_channels = provider.fetch_channels()
    total_fetched = len(all_channels)

    if filter_mode == "groups_selected":
        matched = [c for c in all_channels if c.raw_group_title in active_titles]
    else:
        matched = [c for c in all_channels if matches_filters(c.raw_group_title, settings.group_filters)]

    logger.info(f"Sync: {len(matched)}/{total_fetched} canales coinciden")

    existing = db.load_channels()
    now = time.time()
    new_count = 0
    updated_count = 0

    for pc in matched:
        cid = _channel_id(pc)
        if not cid:
            continue

        if cid in existing:
            ch = existing[cid]
            ch.last_seen_at = now
            ch.logo = pc.logo or ch.logo
            ch.raw_group_title = pc.raw_group_title
            ch.provider_channel_name = pc.name
            # URL solo se actualiza si canal está offline (no interrumpir relay activo)
            if ch.status == ChannelStatus.offline:
                ch.iptv_url = pc.url
            existing[cid] = ch
            updated_count += 1
        else:
            existing[cid] = Channel(
                id=cid,
                name=pc.name,
                logo=pc.logo,
                group=pc.raw_group_title,
                raw_group_title=pc.raw_group_title,
                provider_channel_name=pc.name,
                iptv_url=pc.url,
                status=ChannelStatus.offline,
                imported_at=now,
                last_seen_at=now,
            )
            new_count += 1

    db.save_channels(existing)
    generate_m3u(existing)
    logger.info(f"Sync completado: {new_count} nuevos, {updated_count} actualizados")

    return SyncResult(
        total_fetched=total_fetched,
        matched=len(matched),
        new_channels=new_count,
        updated_channels=updated_count,
        filter_mode=filter_mode,
        warning=warning,
    )
