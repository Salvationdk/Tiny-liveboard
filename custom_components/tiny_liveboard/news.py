"""RSS parsing and cached retrieval from fixed public sources."""
import asyncio
import time
from defusedxml import ElementTree
from homeassistant.helpers.aiohttp_client import async_get_clientsession

SOURCES = {"DR": "https://www.dr.dk/nyheder/service/feeds/allenyheder", "TV 2": "https://feeds.services.tv2.dk/api/feeds/nyheder/rss", "TV2 ØST": "https://www.tv2east.dk/rss", "Kalundborg": "https://news.google.com/rss/search?q=Kalundborg&hl=da&gl=DK&ceid=DK:da"}
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
        self.items = {}
        self.updated = 0
        self.lock = asyncio.Lock()

    async def get(self, selected=None):
        selected = SOURCES.keys() if selected is None else selected
        async with self.lock:
            if time.monotonic() - self.updated < TTL and self.updated:
                return self.combined(selected)
            self.updated = time.monotonic()
            await asyncio.gather(*(self.fetch(name, url) for name, url in SOURCES.items() if name in selected))
            return self.combined(selected)

    def combined(self, selected):
        groups = [self.items.get(name, []) for name in SOURCES if name in selected]
        seen = set()
        result = []
        for i in range(30):
            for group in groups:
                if i < len(group):
                    item = group[i]
                    key = item["title"].casefold()
                    if key not in seen:
                        result.append(item)
                        seen.add(key)
        return result

    async def fetch(self, name, url):
            try:
                session = async_get_clientsession(self.hass)
                async with asyncio.timeout(15):
                    async with session.get(url, allow_redirects=False) as response:
                        response.raise_for_status()
                        if response.status != 200:
                            return
                        payload = await response.content.read(1024 * 1024 + 1)
                        if len(payload) > 1024 * 1024:
                            return
                self.items[name] = [dict(item, source=name) for item in await self.hass.async_add_executor_job(parse_feed, payload)]
            except Exception:
                pass
