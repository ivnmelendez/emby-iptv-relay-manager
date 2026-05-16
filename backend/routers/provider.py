from fastapi import APIRouter, HTTPException
from services.provider import scan, sync, manage_channel, get_provider
from models import GroupSelection
from config import settings
import db

router = APIRouter(prefix="/api/provider", tags=["provider"])


@router.get("/status")
def provider_status():
    """Configuración del proveedor. Sin credenciales."""
    configured = bool(settings.iptv_host and settings.iptv_username and settings.iptv_password)
    groups = db.load_groups()
    selected_count = sum(1 for g in groups.values() if g.selected)
    return {
        "configured": configured,
        "host": settings.iptv_host if configured else None,
        "group_filters_fallback": settings.group_filters,
        "max_active_streams": settings.max_active_streams,
        "groups_scanned": len(groups),
        "groups_selected": selected_count,
    }


@router.post("/scan")
def scan_provider():
    """
    Descarga M3U completa, extrae todos los grupos con conteos y preview.
    NO importa canales. Preserva selección existente.
    """
    try:
        result = scan()
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Error al contactar proveedor: {e}")
    return result


@router.get("/groups")
def list_groups():
    """Lista todos los grupos escaneados, ordenados por count desc."""
    groups = db.load_groups()
    if not groups:
        raise HTTPException(404, "Sin grupos escaneados. Haz POST /api/provider/scan primero.")
    return sorted(groups.values(), key=lambda g: g.count, reverse=True)


@router.get("/groups/selected")
def get_selected_groups():
    """Lista solo los grupos seleccionados para sync."""
    groups = db.load_groups()
    return [g for g in groups.values() if g.selected]


@router.post("/groups/select")
def select_groups(payload: GroupSelection):
    """
    Selecciona qué grupos importar en el próximo sync.
    Reemplaza la selección completa — grupos no listados quedan deseleccionados.
    """
    groups = db.load_groups()
    if not groups:
        raise HTTPException(400, "Sin grupos escaneados. Haz POST /api/provider/scan primero.")

    selected_set = set(payload.groups)
    unknown = [t for t in selected_set if t not in groups]

    for title in groups:
        groups[title].selected = title in selected_set

    db.save_groups(groups)

    selected_count = sum(1 for g in groups.values() if g.selected)
    available_selected = sum(1 for g in groups.values() if g.selected and g.available)

    return {
        "selected": selected_count,
        "available_selected": available_selected,
        "unknown_ignored": unknown,
    }


@router.get("/library")
def list_library():
    """Canales en la library (descubiertos por sync, NO en Emby)."""
    library = db.load_library()
    return sorted(library.values(), key=lambda c: c.name)


@router.post("/library/{channel_id}/manage")
def manage_library_channel(channel_id: str):
    """Promueve canal de library a managed channels (aparece en Emby)."""
    try:
        ch = manage_channel(channel_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return ch


@router.post("/sync")
def sync_provider():
    """
    Importa canales de grupos seleccionados (selected=True, available=True).
    Fallback a GROUP_FILTERS de .env si no hay selección explícita.
    Nunca activa streams.
    """
    try:
        result = sync()
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Error al contactar proveedor: {e}")
    return result
