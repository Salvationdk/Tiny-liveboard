"""Bounded, independent RSS cache and conservative breaking-news policy."""
import asyncio
import time
import logging
import re
import unicodedata
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from defusedxml import ElementTree
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)
SOURCES = {
    "DR": "https://www.dr.dk/nyheder/service/feeds/allenyheder",
    "TV 2": "https://feeds.services.tv2.dk/api/feeds/nyheder/rss",
    "TV2 ØST": "https://news.google.com/rss/search?q=site%3Atv2east.dk+OR+site%3Atv2%C3%B8st.dk&hl=da&gl=DK&ceid=DK:da",
    "Kalundborg": "https://news.google.com/rss/search?q=Kalundborg&hl=da&gl=DK&ceid=DK:da",
    "P4 Sjælland": "https://www.dr.dk/nyheder/service/feeds/regionale/sjaelland",
    "Lokale medier": "https://news.google.com/rss/search?q=Kalundborg+%28site%3Asn.dk+OR+site%3Akalundborgnetavis.dk%29&hl=da&gl=DK&ceid=DK:da",
}
DEFAULT_SOURCES = list(SOURCES)[:4]
TTL = 300
FAILURE_TTL = 60
BREAKING_TTL = 3600
MAX_AGE = 48 * 3600
MAX_BYTES = 1024 * 1024

def timestamp(value):
    if not value:
        return None
    try:
        try:
            dt = parsedate_to_datetime(value)
        except (ValueError, TypeError):
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.replace(tzinfo=dt.tzinfo or timezone.utc).timestamp()
    except (ValueError, TypeError, OverflowError):
        return None

def parse_feed(payload):
    root = ElementTree.fromstring(payload)
    for node in root.iter():
        node.tag = node.tag.rsplit("}", 1)[-1]
    items = []
    for item in root.findall(".//item") + root.findall(".//entry"):
        title = " ".join((item.findtext("title") or "").split())
        if not title:
            continue
        categories = [(c.get("term") or c.text or "").strip().casefold() for c in item.findall("category")]
        published = timestamp(item.findtext("pubDate") or item.findtext("published") or item.findtext("updated"))
        items.append({"title": title[:300], "breaking": bool(set(categories) & {"breaking news", "breaking"}), "published": published})
    return items[:50]

def settings(config):
    sources = config.get("sources", DEFAULT_SOURCES)
    if not isinstance(sources, list):
        sources = DEFAULT_SOURCES
    return [name for name in SOURCES if name in sources]

class NewsEngine:
    def __init__(self, hass):
        self.hass = hass
        self.items = {}
        self.updated = {}
        self.status = {}
        self.lock = asyncio.Lock()

    async def get(self, selected=None):
        selected = DEFAULT_SOURCES if selected is None else [s for s in SOURCES if s in selected]
        async with self.lock:
            now = time.monotonic()
            await asyncio.gather(*(self.fetch(name, SOURCES[name]) for name in selected
                                   if now - self.updated.get(name, -TTL) >= (TTL if self.status.get(name, {}).get("ok", True) else FAILURE_TTL)))
            return self.combined(selected)

    def combined(self, selected, now=None):
        now = time.time() if now is None else now
        result = []
        seen = set()
        groups = [self.items.get(name, []) for name in selected]
        for i in range(50):
            for group in groups:
                if i >= len(group):
                    continue
                item = group[i]
                age = now - (item["published"] or item["received"])
                if age > MAX_AGE or age < -300:
                    continue
                key = re.sub(r"[^\w]+", " ", unicodedata.normalize("NFKC", item["title"]).casefold()).strip()
                if key in seen:
                    continue
                seen.add(key)
                result.append(dict(item, breaking=bool(self.status.get(item["source"], {}).get("ok", True) and item["breaking"] and item["published"] is not None and 0 <= age <= BREAKING_TTL)))
        return sorted(result, key=lambda item: (not item["breaking"], -(item["published"] or item["received"])))[:60]

    async def fetch(self, name, url):
        self.updated[name] = time.monotonic()
        try:
            session = async_get_clientsession(self.hass)
            async with asyncio.timeout(15):
                async with session.get(url, allow_redirects=False) as response:
                    if response.status != 200:
                        raise ValueError(f"HTTP {response.status}")
                    chunks = bytearray()
                    async for chunk in response.content.iter_chunked(16384):
                        chunks.extend(chunk)
                        if len(chunks) > MAX_BYTES:
                            raise ValueError("Feed too large")
            parsed = await self.hass.async_add_executor_job(parse_feed, bytes(chunks))
            previous = {item["title"]: item["received"] for item in self.items.get(name, [])}
            self.items[name] = [dict(item, source=name, received=previous.get(item["title"], time.time())) for item in parsed]
            self.status[name] = {"ok": True, "count": len(parsed), "checked": time.time(), "last_success": time.time()}
        except Exception as exc:
            self.status[name] = {"ok": False, "checked": time.time(), "error": type(exc).__name__, "last_success": self.status.get(name, {}).get("last_success"), "cached_count": len(self.items.get(name, []))}
            _LOGGER.debug("News source %s unavailable: %s", name, type(exc).__name__)
