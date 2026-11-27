from pathlib import Path
import asyncio
import time
from homeassistant.components import frontend, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.helpers.storage import Store
import voluptuous as vol

from .news import NewsEngine, settings
from .alerts import AlertEngine
from .radar import RadarEngine

DOMAIN = "tiny_liveboard"

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
    for profile in profiles.values():
        validate_layout(profile)
    return config

def profile_config(config, name=""):
    profile = config.get("profiles", {}).get(name, {})
    return {**config, **profile} if isinstance(profile, dict) else config

def warnings_enabled(config):
    return bool(config.get("dmiFeed") or any(p.get("dmiFeed") for p in config.get("profiles", {}).values() if isinstance(p, dict)))

async def async_setup_entry(hass, entry):
    store = Store(hass, 1, DOMAIN)
    hass.data[DOMAIN] = {"news": NewsEngine(hass), "alerts": AlertEngine(hass), "radar": RadarEngine(hass), "store": store, "save_lock": asyncio.Lock(), "screens_live": {}, "config": {**entry.data, **(await store.async_load() or {})}}
    if not hass.data.get(DOMAIN + "_registered"):
        await hass.http.async_register_static_paths([StaticPathConfig("/tiny_liveboard", str(Path(__file__).parent / "frontend"), False)])
        websocket_api.async_register_command(hass, get_config)
        websocket_api.async_register_command(hass, save_config)
        websocket_api.async_register_command(hass, get_news)
        websocket_api.async_register_command(hass, get_dmi)
        websocket_api.async_register_command(hass, radar_frames)
        websocket_api.async_register_command(hass, radar_tile)
        websocket_api.async_register_command(hass, screen_heartbeat)
        websocket_api.async_register_command(hass, screen_status)
        hass.data[DOMAIN + "_registered"] = True
    if warnings_enabled(hass.data[DOMAIN]["config"]):
        hass.data[DOMAIN]["alerts"].wis2.start()
    frontend.async_register_built_in_panel(hass, "custom", sidebar_title="Tiny LiveBoard", sidebar_icon="mdi:monitor-dashboard", frontend_url_path="tiny-liveboard", config={"_panel_custom": {"name": "tiny-liveboard-panel", "module_url": "/tiny_liveboard/display.js?v=0.1.4", "embed_iframe": False, "trust_external": False}}, require_admin=False)
    return True

async def async_unload_entry(hass, entry):
    await hass.data[DOMAIN]["alerts"].wis2.stop()
    frontend.async_remove_panel(hass, "tiny-liveboard")
    return True

@websocket_api.websocket_command({vol.Required("type"): "tiny_liveboard/get"})
@websocket_api.async_response
async def get_config(hass, connection, msg):
    connection.send_result(msg["id"], hass.data[DOMAIN]["config"])

@websocket_api.websocket_command({vol.Required("type"): "tiny_liveboard/save", vol.Required("config"): dict, vol.Required("expected_revision"): vol.All(int, vol.Range(min=0))})
@websocket_api.require_admin
@websocket_api.async_response
async def save_config(hass, connection, msg):
    data = hass.data[DOMAIN]
    async with data["save_lock"]:
        revision = data["config"].get("_revision", 0)
        if msg["expected_revision"] != revision:
            connection.send_error(msg["id"], "conflict", "Configuration changed; reopen Studio")
            return
        config = dict(msg["config"], _revision=revision + 1)
        try:
            validate_screen_config(config)
        except (ValueError, TypeError, OverflowError) as err:
            connection.send_error(msg["id"], "invalid_config", str(err))
            return
        await data["store"].async_save(config)
        data["config"] = config
        data["news"].updated.clear()
        if warnings_enabled(config):
            data["alerts"].wis2.start()
        else:
            await data["alerts"].wis2.stop()
        connection.send_result(msg["id"], config)

@websocket_api.websocket_command({vol.Required("type"): "tiny_liveboard/news", vol.Optional("profile", default=""): str})
@websocket_api.async_response
async def get_news(hass, connection, msg):
    data = hass.data[DOMAIN]
    config = data["config"]
    selected = settings(profile_config(config, msg["profile"]))
    items = await data["news"].get(selected)
    connection.send_result(msg["id"], {"items": items, "status": {name: data["news"].status[name] for name in selected if name in data["news"].status}})

@websocket_api.websocket_command({vol.Required("type"): "tiny_liveboard/dmi", vol.Optional("profile", default=""): str})
@websocket_api.async_response
async def get_dmi(hass, connection, msg):
    data = hass.data[DOMAIN]
    if not profile_config(data["config"],msg["profile"]).get("dmiFeed"):
        connection.send_result(msg["id"], {"ok": False, "items": []})
        return
    connection.send_result(msg["id"], await data["alerts"].get())

@websocket_api.websocket_command({vol.Required("type"): "tiny_liveboard/radar_frames", vol.Optional("profile", default=""): str})
@websocket_api.async_response
async def radar_frames(hass, connection, msg):
    try:
        data=hass.data[DOMAIN]
        if not profile_config(data["config"],msg["profile"]).get("externalRadar"): raise ValueError("Disabled")
        connection.send_result(msg["id"], await data["radar"].list())
    except Exception:
        connection.send_error(msg["id"],"radar_unavailable","DMI radar unavailable")

@websocket_api.websocket_command({vol.Required("type"): "tiny_liveboard/radar_tile", vol.Optional("profile", default=""): str,vol.Required("frame"):str,vol.Required("z"):vol.All(int,vol.Range(min=3,max=9)),vol.Required("x"):vol.All(int,vol.Range(min=0,max=511)),vol.Required("y"):vol.All(int,vol.Range(min=0,max=511))})
@websocket_api.async_response
async def radar_tile(hass, connection, msg):
    try:
        data=hass.data[DOMAIN]
        if not profile_config(data["config"],msg["profile"]).get("externalRadar"): raise ValueError("Disabled")
        connection.send_result(msg["id"],await data["radar"].tile(msg["frame"],msg["z"],msg["x"],msg["y"]))
    except Exception:
        connection.send_error(msg["id"],"radar_unavailable","DMI radar tile unavailable")

@websocket_api.websocket_command({vol.Required("type"): "tiny_liveboard/screen_heartbeat",vol.Required("screen"):vol.Match(r"^[a-zA-Z0-9_-]{1,64}$"),vol.Required("profile"):vol.All(str,vol.Length(max=64)),vol.Required("visible"):bool,vol.Required("revision"):vol.All(int,vol.Range(min=0))})
@websocket_api.async_response
async def screen_heartbeat(hass, connection, msg):
    data=hass.data[DOMAIN]
    if msg["screen"] not in data["config"].get("screens",{}):
        connection.send_error(msg["id"],"unknown_screen","Screen not registered")
        return
    live=data["screens_live"]
    live[msg["screen"]]={"last_seen":time.time(),"profile":msg["profile"],"visible":msg["visible"],"revision":msg["revision"]}
    for key in list(live):
        if key not in data["config"].get("screens",{}): live.pop(key,None)
    connection.send_result(msg["id"])

@websocket_api.websocket_command({vol.Required("type"): "tiny_liveboard/screen_status"})
@websocket_api.require_admin
@websocket_api.async_response
async def screen_status(hass, connection, msg):
    data=hass.data[DOMAIN]
    now=time.time()
    result=[]
    for key,profile in data["config"].get("screens",{}).items():
        state=data["screens_live"].get(key,{})
        age=max(0,now-state["last_seen"]) if state else None
        result.append({"screen":key,"assigned_profile":profile,**state,"online":age is not None and age<90,"age":age})
    connection.send_result(msg["id"],result)
