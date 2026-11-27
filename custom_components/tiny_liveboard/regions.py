"""Offline lookup of explicitly identified MeteoAlarm regions."""
import json
import math
from pathlib import Path

def valid_ring(ring):
    return (isinstance(ring, list) and 4 <= len(ring) <= 100000
            and ring[0] == ring[-1]
            and all(isinstance(p, list) and len(p) == 2
                    and all(type(v) in (float, int) and math.isfinite(v) for v in p)
                    and abs(p[0]) <= 180 and abs(p[1]) <= 90 for p in ring)
            and len({tuple(p) for p in ring}) >= 3
            and all(abs(a[0]-b[0]) <= 180 for a,b in zip(ring, ring[1:])))

def load_regions(path):
    path = Path(path)
    if not path.exists():
        return {}
    if path.stat().st_size > 20*1024*1024:
        raise ValueError("Region dataset too large")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("type") != "FeatureCollection":
        raise ValueError("Expected GeoJSON FeatureCollection")
    index = {}
    for feature in data["features"]:
        code = feature.get("properties", {}).get("EMMA_ID")
        if not isinstance(code, str) or not code.startswith("DK"):
            continue
        geometry = feature.get("geometry") or {}
        polygons = geometry.get("coordinates")
        if geometry.get("type") == "Polygon":
            polygons = [polygons]
        elif geometry.get("type") != "MultiPolygon":
            raise ValueError("Unsupported region geometry")
        if not isinstance(polygons, list) or not polygons or not all(
            isinstance(p, list) and p and all(valid_ring(r) for r in p) for p in polygons
        ):
            raise ValueError("Invalid region geometry")
        index.setdefault(code, []).extend(polygons)
    return index

def resolve_regions(item, index):
    if item.get("geometry") or item.get("geometry_status") == "invalid":
        return item
    codes = {g["value"] for g in item.get("geocodes", [])
             if g.get("name", "").upper() == "EMMA_ID"}
    if not codes or not codes.issubset(index):
        return item
    return dict(item, geometry={"type":"MultiPolygon",
                "coordinates":[p for c in sorted(codes) for p in index[c]]},
                geometry_status="available", geometry_source="EMMA_ID")
