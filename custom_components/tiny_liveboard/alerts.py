"""Dedicated MeteoAlarm Atom warning parser and bounded cache."""
import asyncio
import time
from defusedxml import ElementTree
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .news import timestamp

URL = "https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-denmark"

def parse_alerts(payload):
    root = ElementTree.fromstring(payload)
    if root.tag != "{http://www.w3.org/2005/Atom}feed":
        raise ValueError("Not an Atom feed")
    for node in root.iter():
        node.tag = node.tag.rsplit("}", 1)[-1]
    result = []
    seen = set()
    entries = root.findall("entry")
    if len(entries) > 500:
        raise ValueError("Too many alerts")
    recognized = 0
    for entry in entries:
        def get(key):
            return (entry.findtext(key) or "").strip()
        status = get("status").lower()
        message_type = (get("message_type") or get("msgType")).lower()
        if status and message_type:
            recognized += 1
        if status != "actual" or message_type not in ("alert", "update"):
            continue
        if get("scope").lower() != "public":
            continue
        title = get("title") or get("event")
        area = get("areaDesc")
        key = (get("identifier") or get("id"), area, title)
        if not title or key in seen:
            continue
        seen.add(key)
        item = dict(title=title[:500], area=area[:500], severity=get("severity"), effective=get("onset") or get("effective"), expires=get("expires"), description=get("summary")[:2000])
        polygons = []
        invalid_geometry = False
        for p in entry.findall("polygon"):
            try:
                ring = [list(reversed([float(v) for v in pair.split(",")])) for pair in (p.text or "").split()]
                if 4<=len(ring)<=5000 and ring[0]==ring[-1] and all(len(v)==2 and abs(v[0])<=180 and abs(v[1])<=90 for v in ring):
                    polygons.append([ring])
                else:
                    invalid_geometry = True
            except ValueError:
                invalid_geometry = True
        if polygons and not invalid_geometry:
            item["geometry"] = {"type":"MultiPolygon","coordinates":polygons}
        result.append(item)
    if entries and not recognized:
        raise ValueError("Unrecognized warning format")
    return result

class AlertEngine:
    def __init__(self, hass):
        self.hass = hass
        self.lock = asyncio.Lock()
        self.attempt = -300
        self.success = None
        self.ok = False
        self.items = []

    async def get(self):
        async with self.lock:
            if time.monotonic()-self.attempt >= (300 if self.ok else 60):
                self.attempt = time.monotonic()
                try:
                    async with asyncio.timeout(15):
                        async with async_get_clientsession(self.hass).get(URL, allow_redirects=False) as response:
                            if response.status != 200:
                                raise ValueError("HTTP failure")
                            raw = bytearray()
                            async for chunk in response.content.iter_chunked(16384):
                                raw.extend(chunk)
                                if len(raw)>2*1024*1024:
                                    raise ValueError("Oversized feed")
                    self.items = await self.hass.async_add_executor_job(parse_alerts, bytes(raw))
                    self.success = time.time()
                    self.ok = True
                except Exception:
                    self.ok = False
            now = time.time()
            return {"ok":self.ok,"last_success":self.success,"items":[a for a in self.items if timestamp(a["expires"]) is None or timestamp(a["expires"])>now]}
