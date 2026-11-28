"""Home Assistant setup, configuration and WebSocket API for Tiny LiveBoard."""
import asyncio
import logging
import secrets
import time
from datetime import date, timedelta
from functools import wraps
from pathlib import Path

from aiohttp import web
import voluptuous as vol

from homeassistant.auth.permissions.const import POLICY_READ
from homeassistant.components import frontend, websocket_api
from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store

from .agenda import Agenda
from .news import NewsEngine, settings
from .alerts import AlertEngine
from .media import MediaEngine, configured_stream
from .motion import MotionEngine

DOMAIN = "tiny_liveboard"
_LOGGER = logging.getLogger(__name__)

def validate_layout(config):
    import math
    def number(v):
        return type(v) in (int,float) and math.isfinite(v)
    def box(v):
        return isinstance(v,dict) and all(number(v.get(k)) for k in ("x","y","w","h")) and v["x"]>=0 and v["y"]>=0 and v["w"]>=10 and v["h"]>=10 and v["x"]+v["w"]<=100.000001 and v["y"]+v["h"]<=100.000001
    layout=config.get("layout")
    if layout is not None and (not isinstance(layout,dict) or not all(box(layout.get(k)) for k in ("c0","c1","weather"))):
        raise ValueError("Invalid main layout")
    widgets=config.get("widgets",[])
    if not isinstance(widgets,list) or len(widgets)>20:
        raise ValueError("Invalid widget list")
    for widget in widgets:
        if not box(widget) or type(widget.get("z")) is not int or not 0<=widget["z"]<=9:
            raise ValueError("Invalid widget geometry")
        kind=widget.get("kind","state")
        if kind not in ("state","toggle","button","brightness","temperature","history","gauge","lovelace"):
            raise ValueError("Unsupported widget type")
        if kind=="lovelace":
            card=widget.get("card")
            if not isinstance(card,dict) or not isinstance(card.get("type"),str) or not card["type"]:
                raise ValueError("Invalid Lovelace card")
        elif not isinstance(widget.get("entity"),str):
            raise ValueError("Invalid widget entity")
    for key in ("visibility","layers"):
        values=config.get(key,{})
        if not isinstance(values,dict):
            raise ValueError("Invalid "+key)
        for value in values.values():
            if key=="visibility" and type(value) is not bool or key=="layers" and (not number(value) or not 0<=value<=9):
                raise ValueError("Invalid "+key)
    return config

def validate_screen_config(config):
    import re
    import json
    if len(json.dumps(config, allow_nan=False).encode("utf-8")) > 512 * 1024:
        raise ValueError("Configuration too large")
    themes = config.get("themeLibrary", {})
    if not isinstance(themes, dict) or len(themes) > 100:
        raise ValueError("Invalid theme library")
    for name, theme in themes.items():
        if (not 1 <= len(name) <= 64 or name in ("__proto__", "constructor", "prototype")
                or not isinstance(theme, dict) or len(theme) > 100
                or any(type(value) not in (str, int, float) for value in theme.values())):
            raise ValueError("Invalid saved theme")
    profiles = config.get("profiles", {})
    screens = config.get("screens", {})
    schedules = config.get("schedules", [])
    if not isinstance(profiles, dict) or len(profiles) > 100 or any(not isinstance(k,str) or not 1 <= len(k) <= 64 or not isinstance(v,dict) for k,v in profiles.items()):
        raise ValueError("Invalid profiles")
    if not isinstance(screens,dict) or len(screens)>100 or any(not isinstance(k,str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}",k) or not isinstance(v,str) or v not in profiles for k,v in screens.items()):
        raise ValueError("Invalid screen assignments")
    if not isinstance(schedules,list) or len(schedules)>100:
        raise ValueError("Invalid schedules")
    for rule in schedules:
        if not isinstance(rule,dict) or not isinstance(rule.get("screen"),str) or rule["screen"] not in screens or not isinstance(rule.get("profile"),str) or rule["profile"] not in profiles:
            raise ValueError("Unknown scheduled screen or profile")
        days=rule.get("days")
        if not isinstance(days,list) or not days or any(type(d) is not int or not 0<=d<=6 for d in days):
            raise ValueError("Invalid schedule weekdays")
        start,end=rule.get("start"),rule.get("end")
        if not all(isinstance(t,str) and re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]",t) for t in (start,end)) or start==end:
            raise ValueError("Invalid schedule interval")
    validate_layout(config)
    for profile in (config, *profiles.values()):
        users = profile.get("accessUsers", "")
        if not isinstance(users, str) or len(users) > 4096 or any(
            not re.fullmatch(r"[a-zA-Z0-9_-]+", user.strip())
            for user in users.split(",") if user.strip()
        ):
            raise ValueError("Invalid profile users")
        validate_layout(profile)
    return config

def profile_config(config, name=""):
    profile = config.get("profiles", {}).get(name, {})
    return {**config, **profile} if isinstance(profile, dict) else config

def allowed_profile(config, user, name):
    profiles = config.get("profiles", {})
    if name and name not in profiles:
        return False
    if user.is_admin:
        return True
    users = profile_config(config, name).get("accessUsers", "")
    return isinstance(users, str) and (not users or user.id in {value.strip() for value in users.split(",")})


def camera_readable(user, entity):
    return bool(entity and user.permissions.check_entity(entity, POLICY_READ))


def view_config(config, user):
    if user.is_admin:
        return config

    def redact(profile):
        private = {"profiles", "screens", "schedules", "accessUsers", "captureUsers", "themeLibrary",
                   "go2rtc", "customNewsFeeds", "motionConfig"}
        result = {key: value for key, value in profile.items()
                  if key not in private and not key.startswith(("captureRtsp", "stream", "motion"))}
        allowed = user.id in {value.strip() for value in str(profile.get("captureUsers", "")).split(",")}
        result["captureUsers"] = user.id if allowed else ""
        for slot in (0, 1):
            if not camera_readable(user, profile.get(f"camera{slot}")):
                result[f"camera{slot}"] = ""
                result[f"capture{slot}"] = "no"
        return result

    result = redact(config) if allowed_profile(config, user, "") else {"_revision": config.get("_revision", 0)}
    profiles = {name: redact(profile_config(config, name))
                for name in config.get("profiles", {}) if allowed_profile(config, user, name)}
    screens = {name: profile for name, profile in config.get("screens", {}).items() if profile in profiles}
    result.update(profiles=profiles, screens=screens,
                  schedules=[rule for rule in config.get("schedules", [])
                             if rule["screen"] in screens and rule["profile"] in profiles])
    return result


def request_config(hass, connection, msg):
    config = hass.data[DOMAIN]["config"]
    name = msg.get("profile", "")
    if not allowed_profile(config, connection.user, name):
        connection.send_error(msg["id"], "unauthorized", "Dashboard profile not permitted")
        return None
    return profile_config(config, name)


def warnings_enabled(config):
    return bool(config.get("dmiFeed") or any(p.get("dmiFeed") for p in config.get("profiles", {}).values() if isinstance(p, dict)))

class PlaybackView(HomeAssistantView):
    """Serve private captures with a scoped, expiring playback grant."""

    url = "/api/tiny_liveboard/playback/{token}"
    name = "api:tiny_liveboard:playback"
    requires_auth = False

    def __init__(self, hass):
        self.hass = hass

    async def get(self, request, token):
        data = self.hass.data.get(DOMAIN)
        if not data or data.get("closing"):
            raise web.HTTPNotFound()
        grant = data["playback"].get(token)
        if not grant or grant[0] < time.monotonic():
            raise web.HTTPNotFound()
        try:
            path = await self.hass.async_add_executor_job(
                data["media"].playback_file, grant[1], grant[2],
            )
        except (ValueError, OSError) as err:
            raise web.HTTPNotFound() from err
        return web.FileResponse(path, headers={"Cache-Control": "private, no-store",
                                               "Referrer-Policy": "no-referrer"})


def migrate_config(config):
    """Remove retired weather settings from saved dashboards and imports."""
    config = dict(config)
    if "externalRadar" in config:
        config.setdefault("externalWeather", config.pop("externalRadar"))
    config.pop("radarEntity", None)
    if isinstance(config.get("profiles"), dict):
        config["profiles"] = {name: migrate_config(value) if isinstance(value, dict) else value
                              for name, value in config["profiles"].items()}
    return config


async def async_setup_entry(hass, entry):
    store = Store(hass, 1, DOMAIN)
    stored = await store.async_load() or {}
    config = migrate_config({**entry.data, **stored})
    if stored and migrate_config(stored) != stored:
        await store.async_save(config)
    hass.data[DOMAIN] = {"media": MediaEngine(hass), "news": NewsEngine(hass), "agenda": Agenda(hass), "archive": Store(hass, 1, DOMAIN + ".news_archive"), "archive_lock": asyncio.Lock(), "alerts": AlertEngine(hass), "store": store, "save_lock": asyncio.Lock(), "screens_live": {}, "config": config}
    data = hass.data[DOMAIN]
    data["playback"] = {}
    try:
        await hass.async_add_executor_job(data["media"].migrate)
    except (ValueError, OSError):
        _LOGGER.warning("Could not move all legacy camera media into private storage")
    data["motion"] = MotionEngine(hass, data["media"])
    await data["motion"].configure(data["config"])
    if not hass.data.get(DOMAIN + "_registered"):
        await hass.http.async_register_static_paths([StaticPathConfig("/tiny_liveboard", str(Path(__file__).parent / "frontend"), False)])
        hass.http.register_view(PlaybackView(hass))
        websocket_api.async_register_command(hass, get_config)
        websocket_api.async_register_command(hass, camera_media)
        websocket_api.async_register_command(hass, media_gallery)
        websocket_api.async_register_command(hass, motion_history)
        websocket_api.async_register_command(hass, save_config)
        websocket_api.async_register_command(hass, get_news)
        websocket_api.async_register_command(hass, news_archive)
        websocket_api.async_register_command(hass, news_article)
        websocket_api.async_register_command(hass, calendar_events)
        websocket_api.async_register_command(hass, get_dmi)
        websocket_api.async_register_command(hass, screen_heartbeat)
        websocket_api.async_register_command(hass, screen_status)
        hass.data[DOMAIN + "_registered"] = True
    async def cleanup_media(now):
        if data.get("closing"):
            return
        try:
            days = int(data["config"].get("captureRetention", 30) or 30)
            quota = float(data["config"].get("captureQuotaGB", 5) or 5)
        except (ValueError, TypeError):
            return
        if 1 <= days <= 365:
            await hass.async_add_executor_job(data["media"].cleanup, days)
        if 1 <= quota <= 10000:
            await hass.async_add_executor_job(data["media"].enforce_quota, int(quota * 1024**3))
    entry.async_on_unload(async_track_time_interval(hass, cleanup_media, timedelta(hours=1)))
    frontend.async_register_built_in_panel(hass, "custom", sidebar_title="Tiny LiveBoard", sidebar_icon="mdi:monitor-dashboard", frontend_url_path="tiny-liveboard", config={"_panel_custom": {"name": "tiny-liveboard-panel", "module_url": "/tiny_liveboard/display.js?v=0.1.25", "embed_iframe": False, "trust_external": False}}, require_admin=False)
    if warnings_enabled(config):
        data["alerts"].wis2.start()
    return True

async def async_unload_entry(hass, entry):
    data = hass.data[DOMAIN]
    data["closing"] = True
    frontend.async_remove_panel(hass, "tiny-liveboard")
    pending = [task for task in data.get("requests", ()) if not task.done()]
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    async with data["save_lock"]:
        await data["motion"].close()
        await data["media"].close()
        await data["alerts"].wis2.stop()
    data["playback"].clear()
    hass.data.pop(DOMAIN, None)
    return True


def active_response(handler):
    @wraps(handler)
    async def respond(hass, connection, msg):
        data = hass.data.get(DOMAIN)
        if not data or data.get("closing"):
            connection.send_error(msg["id"], "unavailable", "Tiny LiveBoard is starting or reloading")
            return
        requests = data.setdefault("requests", set())
        task = asyncio.current_task()
        requests.add(task)
        try:
            await handler(hass, connection, msg)
        finally:
            requests.discard(task)
    return websocket_api.async_response(respond)


@websocket_api.websocket_command({vol.Required("type"): "tiny_liveboard/get"})
@active_response
async def get_config(hass, connection, msg):
    connection.send_result(msg["id"], view_config(hass.data[DOMAIN]["config"], connection.user))

@websocket_api.websocket_command({vol.Required("type"): "tiny_liveboard/save", vol.Required("config"): dict, vol.Required("expected_revision"): vol.All(int, vol.Range(min=0))})
@websocket_api.require_admin
@active_response
async def save_config(hass, connection, msg):
    data = hass.data[DOMAIN]
    async with data["save_lock"]:
        revision = data["config"].get("_revision", 0)
        if msg["expected_revision"] != revision:
            connection.send_error(msg["id"], "conflict", "Configuration changed; reopen Studio")
            return
        config = migrate_config(dict(msg["config"], _revision=revision + 1))
        try:
            validate_screen_config(config)
        except (ValueError, TypeError, OverflowError) as err:
            connection.send_error(msg["id"], "invalid_config", str(err))
            return
        previous = data["config"]
        await data["store"].async_save(config)
        data["config"] = config
        data["playback"].clear()
        if any(previous.get(key) != config.get(key) for key in previous.keys() | config.keys()
               if key.startswith(("motion", "camera", "captureRtsp"))):
            await data["motion"].configure(config)
        if settings(previous) != settings(config) or previous.get("profiles") != config.get("profiles"):
            data["news"].updated.clear()
        if warnings_enabled(config):
            data["alerts"].wis2.start()
        else:
            await data["alerts"].wis2.stop()
        connection.send_result(msg["id"], config)

@websocket_api.websocket_command({
    vol.Required("type"): "tiny_liveboard/calendar",
    vol.Optional("profile", default=""): vol.All(str, vol.Length(max=64)),
    vol.Required("start"): vol.Match(r"^\d{4}-\d{2}-\d{2}$"),
    vol.Required("end"): vol.Match(r"^\d{4}-\d{2}-\d{2}$"),
})
@active_response
async def calendar_events(hass, connection, msg):
    data = hass.data[DOMAIN]
    config = request_config(hass, connection, msg)
    if config is None:
        return
    try:
        result = await data["agenda"].get(
            connection.user, config,
            date.fromisoformat(msg["start"]), date.fromisoformat(msg["end"]),
        )
    except ValueError:
        connection.send_error(msg["id"], "invalid_range", "Invalid calendar range")
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): "tiny_liveboard/news_article", vol.Required("url"): str, vol.Optional("profile", default=""): vol.All(str, vol.Length(max=64))})
@active_response
async def news_article(hass, connection, msg):
    engine = hass.data[DOMAIN]["news"]
    url = msg["url"]
    config = request_config(hass, connection, msg)
    if config is None:
        return
    selected = settings(config)
    item = engine.find(url, selected)
    if item is None:
        connection.send_error(msg["id"], "not_found", "Article unavailable")
        return
    try:
        result = await engine.metadata(item, selected)
        connection.send_result(msg["id"], result)
    except Exception:
        connection.send_result(msg["id"], {})

@websocket_api.websocket_command({vol.Required("type"): "tiny_liveboard/news_archive", vol.Optional("profile", default=""): vol.All(str, vol.Length(max=64)), vol.Required("action"): vol.In(["list","save","delete"]), vol.Optional("url", default=""): str})
@active_response
async def news_archive(hass, connection, msg):
    import hashlib
    uid = connection.user.id
    data = hass.data[DOMAIN]
    config = request_config(hass, connection, msg) if msg["action"] == "save" else {}
    if config is None:
        return
    async with data["archive_lock"]:
        store = data["archive"]
        archive = await store.async_load() or {}
        entries = archive.get(uid, [])
        url = msg["url"]
        key = hashlib.sha256(url.encode()).hexdigest()
        if msg["action"] == "save":
            selected = settings(config)
            item = data["news"].find(url, selected)
            if item is None:
                connection.send_error(msg["id"], "not_found", "Article is no longer in feed cache")
                return
            if not any(x["id"] == key for x in entries):
                if len(entries) >= 500:
                    connection.send_error(msg["id"], "limit", "Archive limit reached (500)")
                    return
                try:
                    metadata = await data["news"].metadata(item, selected)
                except Exception:
                    metadata = {}
                saved_item = {k: v for k, v in item.items() if k != "_metadata"}
                metadata = metadata or {}
                for field in ("title", "publisher"):
                    if metadata.get(field):
                        saved_item[field] = metadata[field]
                content = metadata.get("article") or metadata.get("body") or ""
                if len(content) > len(saved_item.get("body") or ""):
                    saved_item["body"] = content
                saved_item["article_complete"] = bool(metadata.get("article"))
                saved_item["image"] = metadata.get("image") or saved_item.get("image", "")
                saved_item["original_url"] = metadata.get("url") or url
                if metadata.get("published") is not None:
                    saved_item["published"] = metadata["published"]
                saved_item["article_source"] = metadata.get("article_source", "rss")
                entries.insert(0, {**saved_item, "id": key, "saved": time.time()})
        elif msg["action"] == "delete":
            entries = [x for x in entries if x["id"] != key]
        if msg["action"] != "list":
            if entries:
                archive[uid] = entries
            else:
                archive.pop(uid, None)
            # Oldest saves are removed first when the shared budget is exceeded.
            import json
            total = sum(len(json.dumps(group, ensure_ascii=False).encode()) for group in archive.values())
            while total > 32 * 1024 * 1024:
                owner = min(archive, key=lambda user: archive[user][-1].get("saved", 0))
                group = archive[owner]
                total -= len(json.dumps(group.pop(), ensure_ascii=False).encode()) + 2
                if not group:
                    del archive[owner]
            await store.async_save(archive)
        connection.send_result(msg["id"], {"items": entries})

@websocket_api.websocket_command({vol.Required("type"): "tiny_liveboard/news", vol.Optional("profile", default=""): vol.All(str, vol.Length(max=64))})
@active_response
async def get_news(hass, connection, msg):
    data = hass.data[DOMAIN]
    config = request_config(hass, connection, msg)
    if config is None:
        return
    selected = settings(config)
    items = await data["news"].get(selected)
    connection.send_result(msg["id"], {"items": items, "status": {name: data["news"].status[name] for name in selected if name in data["news"].status}})

@websocket_api.websocket_command({vol.Required("type"): "tiny_liveboard/dmi", vol.Optional("profile", default=""): vol.All(str, vol.Length(max=64))})
@active_response
async def get_dmi(hass, connection, msg):
    data = hass.data[DOMAIN]
    config = request_config(hass, connection, msg)
    if config is None:
        return
    if not config.get("dmiFeed"):
        connection.send_result(msg["id"], {"ok": False, "items": []})
        return
    connection.send_result(msg["id"], await data["alerts"].get())

@websocket_api.websocket_command({vol.Required("type"): "tiny_liveboard/screen_heartbeat",vol.Required("screen"):vol.Match(r"^[a-zA-Z0-9_-]{1,64}$"),vol.Required("profile"):vol.All(str,vol.Length(max=64)),vol.Required("visible"):bool,vol.Required("revision"):vol.All(int,vol.Range(min=0))})
@active_response
async def screen_heartbeat(hass, connection, msg):
    data=hass.data[DOMAIN]
    assigned = data["config"].get("screens", {}).get(msg["screen"])
    if not assigned or not allowed_profile(data["config"], connection.user, assigned):
        connection.send_error(msg["id"],"unknown_screen","Screen not registered")
        return
    if not allowed_profile(data["config"], connection.user, msg["profile"]):
        connection.send_error(msg["id"], "unauthorized", "Dashboard profile not permitted")
        return
    live=data["screens_live"]
    live[msg["screen"]]={"last_seen":time.time(),"profile":msg["profile"],"visible":msg["visible"],"revision":msg["revision"]}
    for key in list(live):
        if key not in data["config"].get("screens",{}): live.pop(key,None)
    connection.send_result(msg["id"])

@websocket_api.websocket_command({vol.Required("type"): "tiny_liveboard/screen_status"})
@websocket_api.require_admin
@active_response
async def screen_status(hass, connection, msg):
    data=hass.data[DOMAIN]
    now=time.time()
    result=[]
    for key,profile in data["config"].get("screens",{}).items():
        state=data["screens_live"].get(key,{})
        age=max(0,now-state["last_seen"]) if state else None
        result.append({"screen":key,"assigned_profile":profile,**state,"online":age is not None and age<90,"age":age})
    connection.send_result(msg["id"],result)

@websocket_api.websocket_command({vol.Required("type"): "tiny_liveboard/camera_media", vol.Required("action"): vol.In(("snapshot","start","stop","status")), vol.Required("entity"): vol.Match(r"^camera\.[a-z0-9_]+$"), vol.Optional("slot"): vol.In((0,1)), vol.Optional("profile", default=""): vol.All(str, vol.Length(max=64)), vol.Optional("minutes", default=30): vol.All(int,vol.Range(min=1,max=60))})
@active_response
async def camera_media(hass, connection, msg):
    engine = hass.data[DOMAIN]["media"]
    entity = msg["entity"]
    cfg = request_config(hass, connection, msg)
    if cfg is None:
        return
    try:
        if not connection.user.is_admin:
            allowed = str(cfg.get("captureUsers","")).split(",")
            slot = msg.get("slot")
            if connection.user.id not in [x.strip() for x in allowed] or slot not in (0,1) or cfg.get("capture"+str(slot)) != "yes" or entity != (cfg.get("camera"+str(slot)) or "camera.tiny_liveboard_direct_"+str(slot)):
                connection.send_error(msg["id"], "unauthorized", "Camera capture not permitted")
                return
            permission = "captureAllowSnapshot" if msg["action"] == "snapshot" else "captureAllowRecord"
            if cfg.get(permission) != "yes" or configured_stream(cfg, slot) or not camera_readable(connection.user, entity):
                connection.send_error(msg["id"], "unauthorized", "Capture action not permitted")
                return
        source = None
        if "slot" in msg:
            source = configured_stream(cfg, msg["slot"])
            if source:
                entity = "camera.tiny_liveboard_direct_"+str(msg["slot"])
        if msg["action"] == "status":
            result = {"recording": entity in engine.jobs, "elapsed": max(0, int(time.monotonic() - engine.started[entity])) if entity in engine.started else 0}
        elif msg["action"] == "stop":
            result = await engine.stop(entity)
        elif msg["action"] == "snapshot":
            result = await engine.snapshot(entity, source)
        else:
            result = await engine.start(entity, msg["minutes"], source)
        connection.send_result(msg["id"], result)
    except Exception:
        connection.send_error(msg["id"], "media_failed", "Camera media operation failed; verify camera stream, FFmpeg and media storage")

@websocket_api.websocket_command({vol.Required("type"): "tiny_liveboard/media_gallery", vol.Optional("profile", default=""): vol.All(str, vol.Length(max=64)), vol.Required("action"): vol.In(("list","delete","resolve","lock","unlock","thumbnail")), vol.Optional("kind"): vol.In(("snapshots","recordings")), vol.Optional("file"): vol.Match(r"^[a-zA-Z0-9_]+\.(jpg|png|mp4)$")})
@active_response
async def media_gallery(hass, connection, msg):
    cfg = request_config(hass, connection, msg)
    if cfg is None:
        return
    if not connection.user.is_admin:
        allowed = [x.strip() for x in str(cfg.get("captureUsers","")).split(",")]
        permission = {"list":"captureAllowGallery","resolve":"captureAllowPlayback","thumbnail":"captureAllowPlayback","delete":"captureAllowDelete","lock":"captureAllowLock","unlock":"captureAllowLock"}[msg["action"]]
        if connection.user.id not in allowed or cfg.get("captureAllowGallery") != "yes" or cfg.get(permission) != "yes":
            connection.send_error(msg["id"], "unauthorized", "Media gallery action not permitted")
            return
    def allowed_file(name):
        if connection.user.is_admin:
            return True
        import re
        match = re.fullmatch(r"(.+)_\d{8}_\d{6}_[a-f0-9]{8}(?:_pre)?\.(?:jpg|png|mp4)", name or "")
        cameras = {(cfg.get("camera"+str(slot)) or "camera.tiny_liveboard_direct_"+str(slot)).replace(".", "_") for slot in (0,1) if cfg.get("capture"+str(slot)) == "yes" and not configured_stream(cfg, slot) and camera_readable(connection.user, cfg.get("camera"+str(slot)))}
        return bool(match and match.group(1) in cameras)
    if msg["action"] != "list" and not allowed_file(msg.get("file")):
        connection.send_error(msg["id"], "unauthorized", "Camera media not permitted")
        return
    engine = hass.data[DOMAIN]["media"]
    try:
        if msg["action"] == "list":
            result = await hass.async_add_executor_job(engine.list_files, None)
            permitted = [item for item in result["items"] if allowed_file(item["file"])]
            result = {"items": permitted[:500], "bytes": sum(item["size"] for item in permitted)}
        elif msg["action"] == "thumbnail":
            result = await engine.thumbnail(msg["file"])
        elif msg["action"] in ("lock", "unlock"):
            result = await hass.async_add_executor_job(engine.set_locked, msg["kind"], msg["file"], msg["action"] == "lock")
        elif msg["action"] == "delete":
            await hass.async_add_executor_job(engine.delete_file, msg["kind"], msg["file"])
            result = {}
        else:
            await hass.async_add_executor_job(engine.playback_file, msg["kind"], msg["file"])
            grants = hass.data[DOMAIN]["playback"]
            now = time.monotonic()
            for key, grant in list(grants.items()):
                if grant[0] < now:
                    del grants[key]
            while len(grants) >= 256:
                del grants[next(iter(grants))]
            token = secrets.token_urlsafe(32)
            grants[token] = (now + 3600, msg["kind"], msg["file"])
            result = {"url": "/api/tiny_liveboard/playback/" + token}
        connection.send_result(msg["id"], result)
    except Exception:
        connection.send_error(msg["id"], "media_failed", "Media operation failed")

@websocket_api.websocket_command({vol.Required("type"): "tiny_liveboard/motion_history", vol.Optional("profile", default=""): vol.All(str, vol.Length(max=64))})
@active_response
async def motion_history(hass, connection, msg):
    history = list(reversed(hass.data[DOMAIN]["motion"].history))
    cfg = request_config(hass, connection, msg)
    if cfg is None:
        return
    if not connection.user.is_admin:
        if connection.user.id not in [x.strip() for x in str(cfg.get("captureUsers","")).split(",")] or cfg.get("captureAllowGallery") != "yes":
            connection.send_error(msg["id"], "unauthorized", "Motion history not permitted")
            return
        cameras = {cfg.get("camera"+str(slot)) or "camera.tiny_liveboard_direct_"+str(slot) for slot in (0,1) if cfg.get("capture"+str(slot)) == "yes" and not configured_stream(cfg, slot) and camera_readable(connection.user, cfg.get("camera"+str(slot)))}
        history = [item for item in history if item.get("camera") in cameras]
    connection.send_result(msg["id"], history)
