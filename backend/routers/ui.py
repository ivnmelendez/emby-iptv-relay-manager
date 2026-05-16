import time
import datetime
import logging
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from config import settings
from models import ChannelStatus
from services import m3u
import db
import state

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ui"])
templates = Jinja2Templates(directory="templates")


# ---------------------------------------------------------------------------
# Jinja2 filters
# ---------------------------------------------------------------------------

def _timeago(ts: float | None) -> str:
    if ts is None:
        return "nunca"
    delta = time.time() - ts
    if delta < 60:
        return f"{int(delta)}s atrás"
    if delta < 3600:
        return f"{int(delta // 60)}m atrás"
    if delta < 86400:
        h, m = int(delta // 3600), int((delta % 3600) // 60)
        return f"{h}h {m}m atrás"
    return f"{int(delta // 86400)}d atrás"


def _uptime(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60}s"
    h, m = s // 3600, (s % 3600) // 60
    return f"{h}h {m}m"


def _fmt_dt(ts: float | None) -> str:
    if ts is None:
        return "—"
    return datetime.datetime.fromtimestamp(ts).strftime("%d %b %H:%M")


templates.env.filters["timeago"] = _timeago
templates.env.filters["uptime"] = _uptime
templates.env.filters["fmt_dt"] = _fmt_dt


# ---------------------------------------------------------------------------
# Shared context
# ---------------------------------------------------------------------------

def _ctx(request: Request, active_page: str) -> dict:
    channels = db.load_channels()
    active_count = sum(1 for c in channels.values() if c.status == ChannelStatus.online)
    return {
        "request": request,
        "active_page": active_page,
        "active_count": active_count,
        "max_streams": settings.max_active_streams,
        "now": time.time(),
    }


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    from services.health import system_status
    channels = db.load_channels()
    groups = db.load_groups()
    active_channels = [c for c in channels.values() if c.status == ChannelStatus.online]
    last_sync = max((c.last_seen_at for c in channels.values() if c.last_seen_at), default=None)

    ctx = _ctx(request, "dashboard")
    ctx.update({
        "channels": channels,
        "active_channels": active_channels,
        "total_channels": len(channels),
        "selected_groups_count": sum(1 for g in groups.values() if g.selected),
        "total_groups_count": len(groups),
        "last_sync": last_sync,
        "health": system_status(),
        "uptime": time.time() - state.server_start,
    })
    return templates.TemplateResponse("dashboard.html", ctx)


@router.get("/channels", response_class=HTMLResponse)
def channels_page(request: Request):
    channels = db.load_channels()
    sorted_channels = sorted(channels.values(), key=lambda c: (c.status.value, c.name))
    ctx = _ctx(request, "channels")
    ctx["channels"] = sorted_channels
    return templates.TemplateResponse("channels.html", ctx)


@router.get("/provider", response_class=HTMLResponse)
def provider_page(request: Request):
    groups = db.load_groups()
    managed = db.load_channels()
    ctx = _ctx(request, "provider")
    ctx.update({
        "groups": sorted(groups.values(), key=lambda g: g.count, reverse=True),
        "provider_host": settings.iptv_host or "No configurado",
        "provider_configured": bool(settings.iptv_host),
        "selected_count": sum(1 for g in groups.values() if g.selected),
        "total_groups": len(groups),
        "managed_count": len(managed),
        "group_filters": settings.group_filters,
        "synced": request.query_params.get("synced"),
    })
    return templates.TemplateResponse("provider.html", ctx)


@router.get("/logs", response_class=HTMLResponse)
def logs_page(request: Request):
    return templates.TemplateResponse("logs.html", _ctx(request, "logs"))


# ---------------------------------------------------------------------------
# HTMX partials
# ---------------------------------------------------------------------------

@router.get("/partials/active-relays", response_class=HTMLResponse)
def partial_active_relays(request: Request):
    channels = db.load_channels()
    active = [c for c in channels.values() if c.status == ChannelStatus.online]
    return templates.TemplateResponse("partials/active_relays_table.html", {
        "request": request,
        "active_channels": active,
        "now": time.time(),
    })


# ---------------------------------------------------------------------------
# Channel actions → returns updated row HTML
# ---------------------------------------------------------------------------

def _row_ctx(request: Request, ch, error: str | None = None) -> dict:
    all_channels = db.load_channels()
    active_count = sum(1 for c in all_channels.values() if c.status == ChannelStatus.online)
    return {
        "request": request,
        "ch": ch,
        "error": error,
        "active_count": active_count,
        "max_streams": settings.max_active_streams,
        "now": time.time(),
    }


@router.post("/ui/channels/{channel_id}/activate", response_class=HTMLResponse)
def ui_activate(channel_id: str, request: Request):
    from services import ffmpeg, m3u, process_manager

    ch = db.get_channel(channel_id)
    if not ch:
        return HTMLResponse("<tr></tr>")

    error = None
    if not ch.iptv_url:
        error = "Sin URL IPTV — haz sync primero"
    elif not process_manager.try_acquire(channel_id):
        error = "Canal en proceso. Intenta en un momento."
    else:
        try:
            ch = db.get_channel(channel_id)
            if not (ch.status == ChannelStatus.online and process_manager.is_running(channel_id)):
                all_channels = db.load_channels()
                active_count = sum(1 for c in all_channels.values() if c.status == ChannelStatus.online)
                if active_count >= settings.max_active_streams:
                    error = f"Límite: máx {settings.max_active_streams} streams activos"
                else:
                    try:
                        pid = ffmpeg.start_relay(channel_id, ch.iptv_url)
                    except RuntimeError as e:
                        error = str(e)
                    else:
                        ch.status = ChannelStatus.online
                        ch.stream_url = ffmpeg.stream_url(channel_id)
                        ch.pid = pid
                        ch.started_at = time.time()
                        db.upsert_channel(ch)
                        m3u.generate_m3u(db.load_channels())
        finally:
            process_manager.release(channel_id)

    return templates.TemplateResponse("partials/channel_row.html", _row_ctx(request, ch, error))


@router.post("/ui/channels/{channel_id}/offline", response_class=HTMLResponse)
def ui_set_offline(channel_id: str, request: Request):
    from services import ffmpeg, m3u, process_manager
    from services.offline import offline_stream_url

    ch = db.get_channel(channel_id)
    if not ch:
        return HTMLResponse("<tr></tr>")

    error = None
    if not process_manager.try_acquire(channel_id):
        error = "Canal en proceso. Intenta en un momento."
    else:
        try:
            ch = db.get_channel(channel_id)
            if ch.status != ChannelStatus.offline:
                ffmpeg.stop_relay(channel_id)
                ch.status = ChannelStatus.offline
                ch.stream_url = offline_stream_url()
                ch.pid = None
                ch.started_at = None
                db.upsert_channel(ch)
                m3u.generate_m3u(db.load_channels())
        finally:
            process_manager.release(channel_id)

    return templates.TemplateResponse("partials/channel_row.html", _row_ctx(request, ch, error))


@router.delete("/ui/channels/{channel_id}", response_class=HTMLResponse)
def ui_delete(channel_id: str):
    from services.ffmpeg import delete_relay_data
    from services.provider import unmanage_channel
    ch = db.get_channel(channel_id)
    if ch:
        delete_relay_data(channel_id)
        db.delete_channel(channel_id)
        unmanage_channel(channel_id)
        from services.m3u import generate_m3u
        generate_m3u(db.load_channels())
    return HTMLResponse("")


# ---------------------------------------------------------------------------
# Provider actions
# ---------------------------------------------------------------------------

def _result_tpl(request: Request, type_: str, message: str):
    return templates.TemplateResponse("partials/action_result.html", {
        "request": request,
        "type": type_,
        "message": message,
    })


@router.post("/ui/provider/scan", response_class=HTMLResponse)
def ui_scan(request: Request):
    from services.provider import scan
    try:
        r = scan()
        return _result_tpl(request, "success",
            f"Scan completado — {r.total_groups} grupos | {r.suggested_groups} sugeridos | {r.new_groups} nuevos")
    except Exception as e:
        return _result_tpl(request, "error", f"Error al contactar proveedor: {str(e)[:120]}")


@router.post("/ui/provider/sync", response_class=HTMLResponse)
def ui_sync(request: Request):
    from services.provider import sync
    from fastapi.responses import Response
    try:
        r = sync()
        if r.warning:
            logger.warning(r.warning)
        resp = Response(status_code=200)
        resp.headers["HX-Redirect"] = "/provider?synced=1"
        return resp
    except Exception as e:
        return _result_tpl(request, "error", str(e)[:140])


@router.post("/ui/provider/groups/toggle", response_class=HTMLResponse)
def ui_toggle_group(request: Request, group_title: str = Form(...)):
    groups = db.load_groups()
    if group_title not in groups:
        logger.warning(f"Group toggle: '{group_title[:60]}' no encontrado en groups.json")
        return HTMLResponse("")
    groups[group_title].selected = not groups[group_title].selected
    db.save_groups(groups)
    selected_count = sum(1 for g in groups.values() if g.selected)
    logger.info(
        f"Group toggle: '{group_title[:50]}' → selected={groups[group_title].selected} "
        f"| total seleccionados: {selected_count}"
    )
    return templates.TemplateResponse("partials/group_row.html", {
        "request": request,
        "g": groups[group_title],
        "selected_count": selected_count,
    })


@router.post("/ui/provider/groups/select-suggested")
def ui_select_suggested():
    groups = db.load_groups()
    for g in groups.values():
        if g.suggested and g.available:
            g.selected = True
    db.save_groups(groups)
    return RedirectResponse("/provider", status_code=303)


@router.post("/ui/provider/groups/clear")
def ui_clear_groups():
    groups = db.load_groups()
    for g in groups.values():
        g.selected = False
    db.save_groups(groups)
    return RedirectResponse("/provider", status_code=303)


# ---------------------------------------------------------------------------
# Library partial + manage action
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Bulk channels actions
# ---------------------------------------------------------------------------

def _sorted_channels():
    channels = db.load_channels()
    return sorted(channels.values(), key=lambda c: (c.status.value, c.name))


def _channels_tbody(request: Request, errors: list | None = None):
    channels = db.load_channels()
    sorted_ch = sorted(channels.values(), key=lambda c: (c.status.value, c.name))
    active_count = sum(1 for c in channels.values() if c.status == ChannelStatus.online)
    return templates.TemplateResponse("partials/channels_tbody.html", {
        "request": request,
        "channels": sorted_ch,
        "active_count": active_count,
        "max_streams": settings.max_active_streams,
        "errors": errors or [],
        "now": time.time(),
    })


@router.post("/ui/channels/bulk/activate", response_class=HTMLResponse)
def ui_bulk_activate(request: Request, ids: str = Form(...)):
    from services import ffmpeg, m3u, process_manager

    channel_ids = [i for i in ids.split(",") if i]
    all_channels = db.load_channels()
    active_count = sum(1 for c in all_channels.values() if c.status == ChannelStatus.online)
    errors = []

    for cid in channel_ids:
        ch = db.get_channel(cid)
        if not ch or ch.status == ChannelStatus.online:
            continue
        if not ch.iptv_url:
            errors.append(f"{ch.name}: sin URL IPTV")
            continue
        if active_count >= settings.max_active_streams:
            errors.append(f"Límite alcanzado: máx {settings.max_active_streams} activos. "
                          f"Activados {active_count - (sum(1 for c in db.load_channels().values() if c.status == ChannelStatus.online) - active_count)} de {len(channel_ids)}.")
            break
        if not process_manager.try_acquire(cid):
            continue
        try:
            pid = ffmpeg.start_relay(cid, ch.iptv_url)
            ch.status = ChannelStatus.online
            ch.stream_url = ffmpeg.stream_url(cid)
            ch.pid = pid
            ch.started_at = time.time()
            db.upsert_channel(ch)
            active_count += 1
        finally:
            process_manager.release(cid)

    m3u.generate_m3u(db.load_channels())
    return _channels_tbody(request, errors)


@router.post("/ui/channels/bulk/offline", response_class=HTMLResponse)
def ui_bulk_offline(request: Request, ids: str = Form(...)):
    from services import ffmpeg, m3u, process_manager
    from services.offline import offline_stream_url

    channel_ids = [i for i in ids.split(",") if i]
    for cid in channel_ids:
        ch = db.get_channel(cid)
        if not ch or ch.status == ChannelStatus.offline:
            continue
        if not process_manager.try_acquire(cid):
            continue
        try:
            ffmpeg.stop_relay(cid)
            ch.status = ChannelStatus.offline
            ch.stream_url = offline_stream_url()
            ch.pid = None
            ch.started_at = None
            db.upsert_channel(ch)
        finally:
            process_manager.release(cid)

    m3u.generate_m3u(db.load_channels())
    return _channels_tbody(request)


@router.post("/ui/channels/bulk/delete", response_class=HTMLResponse)
def ui_bulk_delete(request: Request, ids: str = Form(...)):
    from services.ffmpeg import delete_relay_data
    from services.provider import unmanage_channel

    channel_ids = [i for i in ids.split(",") if i]
    logger.info(f"Bulk delete: {len(channel_ids)} canales — {channel_ids}")
    for cid in channel_ids:
        if db.get_channel(cid):
            delete_relay_data(cid)
            db.delete_channel(cid)
            unmanage_channel(cid)
            logger.info(f"[{cid}] eliminado")

    m3u.generate_m3u(db.load_channels())
    logger.info(f"Bulk delete completado. Quedan: {len(db.load_channels())} canales")
    return _channels_tbody(request)


@router.post("/ui/channels/bulk/clear-offline", response_class=HTMLResponse)
def ui_clear_offline(request: Request):
    from services.ffmpeg import delete_relay_data
    from services.provider import unmanage_channel

    channels = db.load_channels()
    to_delete = [cid for cid, ch in channels.items() if ch.status == ChannelStatus.offline]
    for cid in to_delete:
        delete_relay_data(cid)
        db.delete_channel(cid)
        unmanage_channel(cid)

    m3u.generate_m3u(db.load_channels())
    return _channels_tbody(request)


@router.post("/ui/channels/all/delete", response_class=HTMLResponse)
def ui_delete_all(request: Request):
    from services.ffmpeg import delete_relay_data
    from services.provider import unmanage_channel

    channels = db.load_channels()
    for cid in list(channels.keys()):
        delete_relay_data(cid)
        unmanage_channel(cid)
    db.save_channels({})
    m3u.generate_m3u({})
    return _channels_tbody(request)


# ---------------------------------------------------------------------------
# Library bulk manage
# ---------------------------------------------------------------------------

@router.post("/ui/provider/library/bulk/manage", response_class=HTMLResponse)
def ui_bulk_manage_library(request: Request, ids: str = Form(...)):
    from services.provider import manage_channel

    channel_ids = [i for i in ids.split(",") if i]
    for cid in channel_ids:
        try:
            manage_channel(cid)
        except Exception:
            pass

    library = db.load_library()
    library_sorted = sorted(library.values(), key=lambda c: c.name)
    library_groups = sorted(set(c.raw_group_title for c in library.values()))
    return templates.TemplateResponse("partials/library_section.html", {
        "request": request,
        "library": library_sorted,
        "library_groups": library_groups,
    })


@router.get("/partials/library", response_class=HTMLResponse)
def partial_library(request: Request):
    library = db.load_library()
    library_sorted = sorted(library.values(), key=lambda c: c.name)
    library_groups = sorted(set(c.raw_group_title for c in library.values()))
    return templates.TemplateResponse("partials/library_section.html", {
        "request": request,
        "library": library_sorted,
        "library_groups": library_groups,
    })


@router.post("/ui/provider/library/{channel_id}/manage", response_class=HTMLResponse)
def ui_manage_library(channel_id: str, request: Request):
    from services.provider import manage_channel
    try:
        manage_channel(channel_id)
        library = db.load_library()
        lib_ch = library.get(channel_id)
        if not lib_ch:
            return HTMLResponse("")
        return templates.TemplateResponse("partials/library_channel_row.html", {
            "request": request,
            "lib_ch": lib_ch,
        })
    except Exception as e:
        return HTMLResponse(
            f'<tr><td colspan="3" class="px-5 py-2 text-xs text-red-400">Error: {e}</td></tr>'
        )
