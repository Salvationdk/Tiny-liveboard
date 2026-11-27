from pathlib import Path
import asyncio
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
    hass.data[DOMAIN] = {"news": NewsEngine(hass), "alerts": AlertEngine(hass), "radar": RadarEngine(hass), "store": store, "save_lock": asyncio.Lock(), "config": await store.async_load() or {}}
    if not hass.data.get(DOMAIN + "_registered"):
        await hass.http.async_register_static_paths([StaticPathConfig("/tiny_liveboard", str(Path(__file__).parent / "frontend"), False)])
        websocket_api.async_register_command(hass, get_config)
        websocket_api.async_register_command(hass, save_config)
        websocket_api.async_register_command(hass, get_news)
        websocket_api.async_register_command(hass, get_dmi)
        websocket_api.async_register_command(hass, radar_frames)
        websocket_api.async_register_command(hass, radar_tile)
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
