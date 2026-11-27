"""DMI ODIM composite radar rendering in Web Mercator."""
import asyncio
import base64
import io
import math
import re
import time

API = "https://opendataapi.dmi.dk/v1/radardata"
FILE = re.compile(r"dk\.com\.\d{12}\.500_max\.h5")

def decode_tile(raw, z, x, y):
    if len(raw)>32*1024*1024 or not 3<=z<=9 or not (0<=x<2**z and 0<=y<2**z):
        raise ValueError("Invalid radar request")
    import h5py
    import numpy as np
    from pyproj import CRS, Transformer
    from PIL import Image
    def string(value):
        return value.decode() if isinstance(value, bytes) else str(value)
    with h5py.File(io.BytesIO(raw),"r") as f:
        where=f["where"].attrs
        proj=CRS.from_user_input(string(where["projdef"]))
        transform=Transformer.from_crs("EPSG:4326",proj,always_xy=True)
        left,bottom=transform.transform(float(where["LL_lon"]),float(where["LL_lat"]))
        right,top=transform.transform(float(where["UR_lon"]),float(where["UR_lat"]))
        field=None
        for name in f:
            if not re.fullmatch(r"dataset\d+",name) or not isinstance(f.get(name,getlink=True),h5py.HardLink): continue
            for key in f[name]:
                if not re.fullmatch(r"data\d+",key) or not isinstance(f[name].get(key,getlink=True),h5py.HardLink): continue
                group=f[name][key]
                attrs=group["what"].attrs
                if string(attrs.get("quantity","")) in ("DBZH","TH","DBZ"):
                    if not isinstance(group.get("data",getlink=True),h5py.HardLink): continue
                    field=group["data"]; meta=attrs; break
            if field is not None: break
        if not isinstance(field,h5py.Dataset) or field.ndim!=2 or not 0<field.size<=16000000 or field.dtype.kind not in "iuf" or field.dtype.itemsize>8 or field.is_virtual or field.external:
            raise ValueError("Unsupported radar field")
        h,w=field.shape
        sx,sy=float(where["xscale"]),float(where["yscale"])
        if not all(math.isfinite(v) for v in (left,bottom,right,top,sx,sy)) or min(sx,sy)<=0:
            raise ValueError("Invalid radar projection")
        if abs((right-left)/sx-w)>3 or abs((top-bottom)/sy-h)>3:
            raise ValueError("Inconsistent radar extent")
        a=np.arange(256)+0.5
        lon=(x+a/256)/2**z*360-180
        lat=np.degrees(np.arctan(np.sinh(np.pi*(1-2*(y+a/256)/2**z))))
        xx,yy=transform.transform(*np.meshgrid(lon,lat))
        finite=np.isfinite(xx)&np.isfinite(yy)
        ix=np.floor(np.where(finite,np.clip((xx-left)/sx,-1,w),-1)).astype("int64")
        iy=np.floor(np.where(finite,np.clip((top-yy)/sy,-1,h),-1)).astype("int64")
        valid=finite&(ix>=0)&(ix<w)&(iy>=0)&(iy<h)
        values=field[:][np.clip(iy,0,h-1),np.clip(ix,0,w-1)]
        valid &= (values!=meta["nodata"]) & (values!=meta["undetect"])
        gain,offset=float(meta["gain"]),float(meta["offset"])
        if not math.isfinite(gain) or not math.isfinite(offset) or gain<=0: raise ValueError("Invalid radar calibration")
        dbz=values.astype(float)*gain+offset
        valid &= np.isfinite(dbz)
        rgba=np.zeros((256,256,4),dtype=np.uint8)
        for threshold,color in [(5,(65,155,235,130)),(15,(40,205,190,170)),(25,(60,210,70,190)),(35,(245,220,40,210)),(45,(245,100,35,225)),(55,(220,35,110,240))]:
            rgba[valid & (dbz>=threshold)]=color
        out=io.BytesIO()
        Image.fromarray(rgba).save(out,format="PNG")
        return base64.b64encode(out.getvalue()).decode("ascii")

class RadarEngine:
    def __init__(self,hass):
        self.hass=hass
        self.lock=asyncio.Lock()
        self.frames=[]
        self.updated=0
        self.raw={}
        self.tiles={}
    async def fetch(self,url,limit):
        from homeassistant.helpers.aiohttp_client import async_get_clientsession
        async with asyncio.timeout(25):
            async with async_get_clientsession(self.hass).get(url,allow_redirects=False) as response:
                response.raise_for_status()
                buf=bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    buf.extend(chunk)
                    if len(buf)>limit: raise ValueError("Radar response too large")
                return bytes(buf)
    async def list(self):
        import json
        from .news import timestamp
        async with self.lock:
            if time.monotonic()-self.updated>120 or not self.frames:
                data=json.loads(await self.fetch(API+"/collections/composite/items?scanType=fullRange&sortorder=datetime,DESC&limit=12",1024*1024))
                now=time.time()
                frames=[]
                for f in data["features"]:
                    name=f.get("id","")
                    t=timestamp(f.get("properties",{}).get("datetime"))
                    if FILE.fullmatch(name) and t and now-7200<t<=now+60:
                        frames.append({"id":name,"time":t})
                if not frames: raise ValueError("No current radar frames")
                self.frames=sorted(frames,key=lambda f:f["time"])
                self.updated=time.monotonic()
            return self.frames
    async def tile(self,name,z,x,y):
        if name not in {f["id"] for f in await self.list()}: raise ValueError("Unknown radar frame")
        key=(name,z,x,y)
        async with self.lock:
            if key not in self.tiles:
                if name not in self.raw:
                    self.raw[name]=await self.fetch(API+"/download/"+name,32*1024*1024)
                    while len(self.raw)>3: self.raw.pop(next(iter(self.raw)))
                self.tiles[key]=await self.hass.async_add_executor_job(decode_tile,self.raw[name],z,x,y)
                while len(self.tiles)>48: self.tiles.pop(next(iter(self.tiles)))
            return self.tiles[key]
