"""Dedicated MeteoAlarm Atom warning parser and bounded cache."""
import asyncio
import time
import math
from defusedxml import ElementTree
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .news import timestamp
from pathlib import Path
from .regions import load_regions, resolve_regions
from .wis2 import WIS2Client

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
        if status and message_type and get("scope"):
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
        item = dict(identifier=get('identifier') or get('id'), title=title[:500], area=area[:500], severity=get("severity"), effective=get("onset") or get("effective"), expires=get("expires"), description=get("summary")[:2000])
        # Preserve source region identifiers; never infer a polygon from a region name.
        geocodes = []
        for code in entry.findall("geocode"):
            name = (code.findtext("valueName") or "").strip()
            value = (code.findtext("value") or "").strip()
            if name and value and len(geocodes) < 100:
                geocodes.append({"name": name[:100], "value": value[:200]})
        if geocodes:
            item["geocodes"] = geocodes
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
        # CAP circles use latitude,longitude and radius in kilometres.
        for circle in entry.findall("circle"):
            try:
                center, radius = (circle.text or "").split()
                lat, lon = map(float, center.split(","))
                radius = float(radius)
                if not (-90 < lat < 90 and -180 <= lon <= 180 and 0 < radius <= 1000):
                    raise ValueError("Invalid circle")
                phi, lam, angular = math.radians(lat), math.radians(lon), radius / 6371.0088
                ring = []
                for i in range(72):
                    bearing = i * math.tau / 72
                    dest = math.asin(math.sin(phi)*math.cos(angular)+math.cos(phi)*math.sin(angular)*math.cos(bearing))
                    dl = math.atan2(math.sin(bearing)*math.sin(angular)*math.cos(phi),math.cos(angular)-math.sin(phi)*math.sin(dest))
                    ring.append([((math.degrees(lam+dl)+180)%360)-180, math.degrees(dest)])
                ring.append(ring[0])
                if any(abs(a[0]-b[0])>180 for a,b in zip(ring,ring[1:])):
                    raise ValueError("Dateline crossing")
                polygons.append([ring])
            except (ValueError, OverflowError):
                invalid_geometry = True
        if polygons and not invalid_geometry:
            item["geometry"] = {"type":"MultiPolygon","coordinates":polygons}
        item["geometry_status"] = "available" if "geometry" in item else "invalid" if invalid_geometry else "unresolved_region" if geocodes else "missing"
        result.append(item)
    if entries and recognized != len(entries):
        raise ValueError("Unrecognized warning format")
    return result

def active_alerts(items, now):
    """Exclude expired, future and invalid timestamp warnings."""
    result = []
    for item in items:
        start = timestamp(item.get("effective"))
        end = timestamp(item.get("expires"))
        if (item.get("effective") and start is None) or (item.get("expires") and end is None):
            continue
        if (start is None or start <= now) and (end is None or end > now):
            result.append(item)
    return result

def parse_with_regions(payload, path):
    items = parse_alerts(payload)
    try:
        index = load_regions(path)
    except (OSError, ValueError, TypeError, KeyError):
        index = {}
    return [resolve_regions(item, index) for item in items]

class AlertEngine:
    def __init__(self, hass):
        self.hass = hass
        self.lock = asyncio.Lock()
        self.attempt = -300
        self.success = None
        self.ok = False
        self.items = []
        self.wis2 = WIS2Client(hass)

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
                    self.items = await self.hass.async_add_executor_job(parse_with_regions, bytes(raw), Path(self.hass.config.path('tiny_liveboard_emma.geojson')))
                    self.success = time.time()
                    self.ok = True
                except Exception:
                    self.ok = False
            now = time.time()
            self.wis2.index.prune(now)
            live=self.wis2.index.items(now)
            ids={i["identifier"] for i in live}
            removed=self.wis2.index.removed
            fallback=[i for i in self.items if i.get("identifier") not in ids and i.get("identifier") not in removed]
            return {"ok":self.ok,"last_success":self.success,"wis2_connected":self.wis2.connected,"wis2_last_success":self.wis2.last_success,"items":active_alerts(fallback+live, now)}
