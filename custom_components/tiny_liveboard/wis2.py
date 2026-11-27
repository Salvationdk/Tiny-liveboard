"""MeteoAlarm WIS2 notification and precise geometry decoding."""
import json
from urllib.parse import urlsplit
from .regions import valid_ring

TOPIC = "origin/a/wis2/eu-eumetnet-warnings/data/core/weather/advisories-warnings"

def notification(payload):
    if len(payload) > 256 * 1024:
        raise ValueError("Oversize notification")
    data = json.loads(payload)
    if not isinstance(data, dict) or data.get("type") != "Feature":
        return None
    props = data.get("properties") or {}
    if props.get("countryCode") != "DK":
        return None
    links = {}
    for link in data.get("links", []):
        rel = link.get("rel")
        if rel not in ("geometry", "xml"):
            continue
        href = link.get("href", "")
        url = urlsplit(href)
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.port not in (None, 443):
            raise ValueError("Unsafe resource URL")
        links[rel] = href
    if not props.get("alertId") or "geometry" not in links or "xml" not in links:
        return None
    return {"id": props["alertId"], "feature_id": data.get("id"), "links": links,
            "references": props.get("referencedAlertIds", []),
            "index_info": props.get("indexInfo"), "index_area": props.get("indexArea")}

def exact_geometry(payload):
    if len(payload) > 4 * 1024 * 1024:
        raise ValueError("Oversize geometry")
    data = json.loads(payload)
    features = data.get("features") if data.get("type") == "FeatureCollection" else [data]
    polygons = []
    for feature in features:
        geometry = feature.get("geometry") if feature.get("type") == "Feature" else feature
        kind = geometry.get("type")
        coords = geometry.get("coordinates")
        if kind == "Polygon":
            coords = [coords]
        elif kind != "MultiPolygon":
            raise ValueError("Unsupported geometry")
        if not isinstance(coords, list) or not coords or not all(isinstance(p, list) and p and all(valid_ring(r) for r in p) for p in coords):
            raise ValueError("Invalid geometry")
        polygons.extend(coords)
    if not polygons:
        raise ValueError("Empty geometry")
    return {"type":"MultiPolygon","coordinates":polygons}
