from pathlib import Path
from homeassistant.components import frontend, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.helpers.storage import Store
import voluptuous as vol

from .news import NewsEngine, settings

DOMAIN = "tiny_liveboard"

async def async_setup_entry(hass, entry):
    store = Store(hass, 1, DOMAIN)
    hass.data[DOMAIN] = {"news": NewsEngine(hass), "store": store, "config": await store.async_load() or {}}
    if not hass.data.get(DOMAIN + "_registered"):
        await hass.http.async_register_static_paths([StaticPathConfig("/tiny_liveboard", str(Path(__file__).parent / "frontend"), False)])
        websocket_api.async_register_command(hass, get_config)
        websocket_api.async_register_command(hass, save_config)
        websocket_api.async_register_command(hass, get_news)
        websocket_api.async_register_command(hass, get_dmi)
        hass.data[DOMAIN + "_registered"] = True
    frontend.async_register_built_in_panel(hass, "custom", sidebar_title="Tiny LiveBoard", sidebar_icon="mdi:monitor-dashboard", frontend_url_path="tiny-liveboard", config={"_panel_custom": {"name": "tiny-liveboard", "module_url": "/tiny_liveboard/display.js", "embed_iframe": False, "trust_external": False}}, require_admin=False)
    return True

async def async_unload_entry(hass, entry):
    frontend.async_remove_panel(hass, "tiny-liveboard")
    return True

@websocket_api.websocket_command({vol.Required("type"): "tiny_liveboard/get"})
@websocket_api.async_response
async def get_config(hass, connection, msg):
    connection.send_result(msg["id"], hass.data[DOMAIN]["config"])

@websocket_api.websocket_command({vol.Required("type"): "tiny_liveboard/save", vol.Required("config"): dict})
@websocket_api.require_admin
@websocket_api.async_response
async def save_config(hass, connection, msg):
    data = hass.data[DOMAIN]
    await data["store"].async_save(msg["config"])
    data["config"] = msg["config"]
    data["news"].updated.clear()
    connection.send_result(msg["id"])

@websocket_api.websocket_command({vol.Required("type"): "tiny_liveboard/news"})
@websocket_api.async_response
async def get_news(hass, connection, msg):
    data = hass.data[DOMAIN]
    items = await data["news"].get(settings(data["config"]))
    connection.send_result(msg["id"], {"items": items, "status": data["news"].status})

@websocket_api.websocket_command({vol.Required("type"): "tiny_liveboard/dmi"})
@websocket_api.async_response
async def get_dmi(hass, connection, msg):
    data = hass.data[DOMAIN]
    if not data["config"].get("dmiFeed"):
        connection.send_result(msg["id"], {"ok": False, "items": []})
        return
    engine = data["news"]
    async with engine.lock:
        import time
        if time.monotonic() - engine.updated.get("DMI", -300) >= 300:
            await engine.fetch("DMI", "https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-denmark")
        connection.send_result(msg["id"], {"ok": engine.status.get("DMI", {}).get("ok", False), "items": engine.items.get("DMI", [])})
