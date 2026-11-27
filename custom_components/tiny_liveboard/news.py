"""RSS parsing and cached retrieval from fixed public sources."""
import asyncio
import time
from defusedxml import ElementTree
from homeassistant.helpers.aiohttp_client import async_get_clientsession

SOURCES = {"dr": "https://www.dr.dk/nyheder/service/feeds/allenyheder"}
TTL = 300

def parse_feed(payload):
    root = ElementTree.fromstring(payload)
    items = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        categories = [(c.text or "").strip().casefold() for c in item.findall("category")]
        items.append({"title": title[:300], "breaking": "breaking news" in categories or "breaking" in categories})
    return items[:30]

class NewsEngine:
    def __init__(self, hass):
        self.hass = hass
        self.items = []
        self.updated = 0
        self.lock = asyncio.Lock()

    async def get(self):
        async with self.lock:
            if time.monotonic() - self.updated < TTL and self.updated:
                return self.items
            self.updated = time.monotonic()
            try:
                session = async_get_clientsession(self.hass)
                async with asyncio.timeout(15):
                    async with session.get(SOURCES["dr"], allow_redirects=False) as response:
                        response.raise_for_status()
                        if response.status != 200:
                            return self.items
                        payload = await response.content.read(1024 * 1024 + 1)
                        if len(payload) > 1024 * 1024:
                            return self.items
                self.items = await self.hass.async_add_executor_job(parse_feed, payload)
            except Exception:
                pass
            return self.items
