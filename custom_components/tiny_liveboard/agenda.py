"""Read configured calendars with the connected Home Assistant user's permissions."""
import asyncio
from datetime import date, datetime, time, timedelta, timezone
import re
from zoneinfo import ZoneInfo

from homeassistant.auth.permissions.const import POLICY_READ
from homeassistant.components.calendar import CalendarEntity
from homeassistant.components.calendar.const import DATA_COMPONENT

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
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=zone)
        if isinstance(value, date):
            return datetime.combine(value, time.min, zone)
        if DATE.fullmatch(value):
            return datetime.combine(date.fromisoformat(value), time.min, zone)
        result = datetime.fromisoformat(value)
        return result if result.tzinfo else result.replace(tzinfo=zone)

    start, end = event["start"], event["end"]
    start_time, end_time = parse(start), parse(end)
    if end_time.timestamp() <= start_time.timestamp():
        raise ValueError("Invalid calendar interval")
    all_day = (isinstance(start, date) and not isinstance(start, datetime)) or (isinstance(start, str) and bool(DATE.fullmatch(start)))
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
            result = await self._query(entities, zone, start, end)
            self.cache = {k: v for k, v in self.cache.items() if v[0] > now and k != key}
            if len(self.cache) >= 32:
                self.cache.pop(next(iter(self.cache)))
            self.cache[key] = (asyncio.get_running_loop().time() + (30 if result["unavailable"] else 120), result)
            return result

    async def _query(self, entities, zone, start, end):
        component = self.hass.data.get(DATA_COMPONENT)
        if component is None:
            return {"items": [], "unavailable": True}
        start_at = datetime.combine(start, time.min, zone)
        end_at = datetime.combine(end, time.min, zone)

        async def read(entity):
            calendar = component.get_entity(entity)
            if not isinstance(calendar, CalendarEntity) or not calendar.available:
                return None
            try:
                events = await asyncio.wait_for(
                    calendar.async_get_events(self.hass, start_at, end_at), timeout=10,
                )
            except Exception:
                return None
            result = []
            for event in events[:MAX_EVENTS]:
                try:
                    result.append(normalize_event({
                        "start": event.start, "end": event.end, "summary": event.summary,
                        "location": event.location,
                    }, entity, zone))
                except (AttributeError, ValueError, TypeError, OverflowError):
                    continue
            return result

        groups = await asyncio.gather(*(read(entity) for entity in entities))
        items = [item for group in groups if group is not None for item in group]
        items.sort(key=lambda item: (item["when"], item["entity"], item["title"]))
        return {"items": items[:MAX_EVENTS], "unavailable": any(group is None for group in groups)}
