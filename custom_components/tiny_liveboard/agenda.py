"""Read configured calendars with the connected Home Assistant user's permissions."""
import asyncio
from datetime import date, datetime, time, timedelta, timezone
import re
from zoneinfo import ZoneInfo

from homeassistant.auth.permissions.const import POLICY_READ
from homeassistant.core import Context

MAX_CALENDARS = 8
MAX_EVENTS = 300
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def configured_calendars(config):
    value = config.get("calendars", "")
    if not isinstance(value, str):
        return []
    return list(dict.fromkeys(
        entity for entity in re.split(r"[\s,]+", value)[:64]
        if re.fullmatch(r"calendar\.[a-z0-9_]{1,120}", entity)
    ))[:MAX_CALENDARS]


def normalize_event(event, entity, zone):
    def parse(value):
        if DATE.fullmatch(value):
            return datetime.combine(date.fromisoformat(value), time.min, zone)
        result = datetime.fromisoformat(value)
        return result if result.tzinfo else result.replace(tzinfo=zone)

    start, end = event["start"], event["end"]
    start_time, end_time = parse(start), parse(end)
    if end_time.timestamp() <= start_time.timestamp():
        raise ValueError("Invalid calendar interval")
    all_day = bool(DATE.fullmatch(start))
    first_day = start_time.astimezone(zone).date()
    last_day = (end_time.astimezone(timezone.utc) - timedelta(microseconds=1)).astimezone(zone).date()
    return {
        "entity": entity,
        "title": str(event.get("summary") or entity)[:300],
        "location": str(event.get("location") or "")[:300],
        "when": start_time.timestamp(),
        "until": end_time.timestamp(),
        "allDay": all_day,
        "startDay": first_day.isoformat(),
        "endDay": last_day.isoformat(),
    }


class Agenda:
    """Keep a small per-user cache and coalesce concurrent calendar reads."""

    def __init__(self, hass):
        self.hass = hass
        self.cache = {}
        self.lock = asyncio.Lock()

    async def get(self, user, config, start, end):
        zone = ZoneInfo(self.hass.config.time_zone)
        today = datetime.now(zone).date()
        if not 0 < (end - start).days <= 45 or abs((start - today).days) > 3660:
            raise ValueError("Invalid calendar range")
        entities = tuple(entity for entity in configured_calendars(config)
                         if user.permissions.check_entity(entity, POLICY_READ))
        if not entities:
            return {"items": [], "unavailable": False}
        key = (user.id, entities, zone.key, start, end)
        async with self.lock:
            now = asyncio.get_running_loop().time()
            cached = self.cache.get(key)
            if cached and now < cached[0]:
                return cached[1]
            result = await self._query(user.id, entities, zone, start, end)
            self.cache = {k: v for k, v in self.cache.items() if v[0] > now and k != key}
            if len(self.cache) >= 32:
                self.cache.pop(next(iter(self.cache)))
            self.cache[key] = (asyncio.get_running_loop().time() + (30 if result["unavailable"] else 120), result)
            return result

    async def _query(self, user_id, entities, zone, start, end):
        if not self.hass.services.has_service("calendar", "get_events"):
            return {"items": [], "unavailable": True}

        async def read(entity):
            try:
                response = await asyncio.wait_for(self.hass.services.async_call(
                    "calendar", "get_events",
                    {"entity_id": entity, "start_date_time": datetime.combine(start, time.min, zone).isoformat(),
                     "end_date_time": datetime.combine(end, time.min, zone).isoformat()},
                    blocking=True, return_response=True, context=Context(user_id=user_id),
                ), timeout=10)
                events = response[entity]["events"]
            except Exception:
                return None
            result = []
            for event in events[:MAX_EVENTS]:
                try:
                    result.append(normalize_event(event, entity, zone))
                except (KeyError, ValueError, TypeError, OverflowError):
                    continue
            return result

        groups = await asyncio.gather(*(read(entity) for entity in entities))
        items = [item for group in groups if group is not None for item in group]
        items.sort(key=lambda item: (item["when"], item["entity"], item["title"]))
        return {"items": items[:MAX_EVENTS], "unavailable": any(group is None for group in groups)}
