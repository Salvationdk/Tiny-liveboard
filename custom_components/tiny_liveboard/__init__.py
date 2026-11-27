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

async def async_setup_entry(hass, entry):
    store = Store(hass, 1, DOMAIN)
    hass.data[DOMAIN] = {"news": NewsEngine(hass), "alerts": AlertEngine(hass), "radar": RadarEngine(hass), "store": store, "save_lock": asyncio.Lock(), "screens_live": {}, "config": await store.async_load() or {}}
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
    if hass.data[DOMAIN]["config"].get("dmiFeed"):
        hass.data[DOMAIN]["alerts"].wis2.start()
    frontend.async_register_built_in_panel(hass, "custom", sidebar_title="Tiny LiveBoard", sidebar_icon="mdi:monitor-dashboard", frontend_url_path="tiny-liveboard", config={"_panel_custom": {"name": "tiny-liveboard", "module_url": "/tiny_liveboard/display.js", "embed_iframe": False, "trust_external": False}}, require_admin=False)
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
        await data["store"].async_save(config)
        data["config"] = config
        data["news"].updated.clear()
        if config.get("dmiFeed"):
            data["alerts"].wis2.start()
        else:
            await data["alerts"].wis2.stop()
        connection.send_result(msg["id"], config)

@websocket_api.websocket_command({vol.Required("type"): "tiny_liveboard/news"})
@websocket_api.async_response
async def get_news(hass, connection, msg):
    data = hass.data[DOMAIN]
    selected = settings(data["config"])
    items = await data["news"].get(selected)
    connection.send_result(msg["id"], {"items": items, "status": {name: data["news"].status[name] for name in selected if name in data["news"].status}})

@websocket_api.websocket_command({vol.Required("type"): "tiny_liveboard/dmi"})
@websocket_api.async_response
async def get_dmi(hass, connection, msg):
    data = hass.data[DOMAIN]
    if not data["config"].get("dmiFeed"):
        connection.send_result(msg["id"], {"ok": False, "items": []})
        return
    connection.send_result(msg["id"], await data["alerts"].get())

@websocket_api.websocket_command({vol.Required("type"): "tiny_liveboard/radar_frames"})
@websocket_api.async_response
async def radar_frames(hass, connection, msg):
    try:
        data=hass.data[DOMAIN]
        if not data["config"].get("externalRadar"): raise ValueError("Disabled")
        connection.send_result(msg["id"], await data["radar"].list())
    except Exception:
        connection.send_error(msg["id"],"radar_unavailable","DMI radar unavailable")

@websocket_api.websocket_command({vol.Required("type"): "tiny_liveboard/radar_tile",vol.Required("frame"):str,vol.Required("z"):vol.All(int,vol.Range(min=3,max=9)),vol.Required("x"):vol.All(int,vol.Range(min=0,max=511)),vol.Required("y"):vol.All(int,vol.Range(min=0,max=511))})
@websocket_api.async_response
async def radar_tile(hass, connection, msg):
    try:
        data=hass.data[DOMAIN]
        if not data["config"].get("externalRadar"): raise ValueError("Disabled")
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
