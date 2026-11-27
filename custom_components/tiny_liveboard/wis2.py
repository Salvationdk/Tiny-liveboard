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


def parse_cap(payload, notice, geometry=None):
    """Decode CAP metadata; never use the notification bounding box."""
    from defusedxml import ElementTree
    from .news import timestamp
    if len(payload) > 2*1024*1024:
        raise ValueError("Oversize CAP")
    root = ElementTree.fromstring(payload)
    if root.tag != "{urn:oasis:names:tc:emergency:cap:1.2}alert":
        raise ValueError("Invalid CAP root")
    for node in root.iter():
        node.tag = node.tag.rsplit("}",1)[-1]
    def get(node,key):
        return (node.findtext(key) or "").strip()
    if get(root,"status") != "Actual" or get(root,"scope") != "Public":
        return None
    kind = get(root,"msgType")
    identifier = get(root,"identifier")
    sent = timestamp(get(root,"sent"))
    if not identifier or sent is None or kind not in ("Alert","Update","Cancel"):
        return None
    refs = []
    for ref in get(root,"references").split():
        parts = ref.split(",")
        if len(parts)==3:
            refs.append(parts[1])
    if kind == "Cancel":
        return {"id":identifier,"sent":sent,"references":refs,"items":[]}
    infos = root.findall("info")
    index = notice.get("index_info")
    if type(index) is not int or not 0 <= index < len(infos):
        if len(infos)!=1:
            return None
        index=0
    info=infos[index]
    areas=info.findall("area")
    area_index=notice.get("index_area")
    if type(area_index) is int and 0 <= area_index < len(areas):
        areas=[areas[area_index]]
    elif len(areas)!=1:
        return None
    end=get(info,"expires")
    if timestamp(end) is None:
        return None
    item={"title":get(info,"headline") or get(info,"event"),"area":get(areas[0],"areaDesc"),
          "severity":get(info,"severity"),"effective":get(info,"onset") or get(info,"effective") or get(root,"sent"),
          "expires":end,"description":get(info,"description")[:2000],"identifier":identifier,
          "geometry_status":"available" if geometry else "missing"}
    if geometry:
        item["geometry"]=geometry
        item["geometry_source"]="WIS2"
    return {"id":identifier,"sent":sent,"references":refs,"items":[item]}

class WarningIndex:
    """Bounded in-memory CAP revision index, including cancellation tombstones."""
    def __init__(self):
        self.records={}
        self.removed={}
    def apply(self,event,feature_id,now):
        if not event:
            return
        identifier=event["id"]
        sent=event["sent"]
        if sent <= self.removed.get(identifier,float("-inf")):
            return
        for ref in event["references"]:
            self.removed[ref]=max(sent,self.removed.get(ref,float("-inf")))
            for key,record in list(self.records.items()):
                if record["id"]==ref and record["sent"]<=sent:
                    del self.records[key]
        key=(identifier,str(feature_id))
        if event["items"] and sent>=self.records.get(key,{}).get("sent",float("-inf")):
            self.records[key]=event
        self.prune(now)
    def prune(self,now):
        from .news import timestamp
        self.records={k:v for k,v in self.records.items() if any((timestamp(i.get("expires")) or 0)>now for i in v["items"])}
        self.removed={k:v for k,v in self.removed.items() if v>now-7*86400}
        for mapping in (self.records,self.removed):
            while len(mapping)>1000:
                del mapping[next(iter(mapping))]
    def items(self,now):
        self.prune(now)
        return [item for event in self.records.values() for item in event["items"]]
