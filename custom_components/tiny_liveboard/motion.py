"""Low-resolution motion analysis using FFmpeg, without Python image dependencies."""
import asyncio
import shutil
import time
import re
from collections import deque
from homeassistant.helpers.storage import Store
import json

def motion_level(previous, current, mask=None):
    if not previous or len(previous) != len(current):
        return 0.0
    indices = mask if mask is not None else range(len(current))
    return 100 * sum(abs(previous[i]-current[i]) >= 25 for i in indices) / max(1,len(indices))

class MotionEngine:
    def __init__(self, hass, media):
        self.hass, self.media = hass, media
        self.tasks = []
        self.history = deque(maxlen=200)
        self.owned = {}
        self.store = Store(hass, 1, 'tiny_liveboard_motion')
        self.loaded = False

    async def configure(self, cfg):
        await self.close()
        if not self.loaded:
            self.history.extend((await self.store.async_load() or {}).get('items', [])[-200:])
            self.loaded = True
        seen = set()
        for i in range(2):
            entity = cfg.get("camera"+str(i), "")
            if cfg.get("motion"+str(i)) == "yes" and re.fullmatch(r"camera\.[a-z0-9_]+", entity or "") and entity not in seen:
                seen.add(entity)
                self.tasks.append(asyncio.create_task(self.run(entity, cfg, str(i))))

    async def close(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()

    async def run(self, entity, cfg, i):
        from homeassistant.components.camera import async_get_stream_source
        sensor = "binary_sensor.tiny_liveboard_camera_"+str(int(i)+1)+"_motion"
        level_sensor = "sensor.tiny_liveboard_camera_"+str(int(i)+1)+"_motion_level"
        def number(key, default, low, high):
            try:
                return max(low,min(high,int(cfg.get(key+i,default))))
            except (ValueError,TypeError):
                return default
        sensitivity = number("motionSensitivity",65,1,100)
        threshold = 1 + (100-sensitivity)*0.19
        post = number("motionPost",20,5,120)
        fps = number("motionFps",2,1,5)
        mask = zone_mask(cfg.get('motionZones'+i,'[]'), cfg.get('motionExclude'+i,'[]'))
        try:
            while True:
                proc = None
                try:
                    source = await asyncio.wait_for(async_get_stream_source(self.hass,entity),15)
                    ffmpeg = await self.hass.async_add_executor_job(shutil.which,"ffmpeg")
                    if not source or not ffmpeg:
                        raise ValueError("Stream unavailable")
                    proc = await asyncio.create_subprocess_exec(ffmpeg,"-nostdin","-loglevel","error","-i",source,"-an","-vf",f"fps={fps},scale=160:90,format=gray","-f","rawvideo","-pix_fmt","gray","pipe:1",stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
                    previous = None
                    last = 0
                    hits = 0
                    active = False
                    while True:
                        frame = await asyncio.wait_for(proc.stdout.readexactly(14400),15)
                        level = motion_level(previous,frame,mask)
                        bounds = motion_bounds(previous,frame,mask)
                        previous = frame
                        now = time.monotonic()
                        hits = hits+1 if level >= threshold else 0
                        self.hass.states.async_set(level_sensor,round(level,2),{"unit_of_measurement":"%","camera":entity,"bounds":bounds})
                        if hits >= 2:
                            last = now
                            if not active:
                                active = True
                                self.history.append({"camera":entity,"time":time.time(),"level":level})
                                self.store.async_delay_save(lambda: {"items":list(self.history)}, 5)
                                self.hass.bus.async_fire("tiny_liveboard_motion",{"camera":entity,"level":level})
                                self.hass.states.async_set(sensor,"on",{"device_class":"motion","camera":entity})
                                if cfg.get("motionSnapshot"+i) == "yes":
                                    try:
                                        await self.media.snapshot(entity)
                                    except Exception:
                                        pass
                                if cfg.get("motionRecord"+i) == "yes" and entity not in self.media.jobs:
                                    try:
                                        await self.media.start(entity,30)
                                        self.owned[entity] = self.media.jobs[entity][0]
                                    except Exception:
                                        pass
                        if active and now-last >= post:
                            active = False
                            self.hass.states.async_set(sensor,"off",{"device_class":"motion","camera":entity})
                            await self.stop_owned(entity)
                        elif not active:
                            self.hass.states.async_set(sensor,"off",{"device_class":"motion","camera":entity})
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self.hass.states.async_set(sensor,"unavailable",{"device_class":"motion"})
                    self.hass.states.async_set(level_sensor,"unavailable")
                finally:
                    if proc and proc.returncode is None:
                        proc.kill()
                        await proc.wait()
                    await self.stop_owned(entity)
                await asyncio.sleep(10)
        finally:
            self.hass.states.async_remove(sensor)
            self.hass.states.async_remove(level_sensor)

    async def stop_owned(self, entity):
        proc = self.owned.pop(entity,None)
        if proc is not None and self.media.jobs.get(entity,(None,))[0] is proc:
            await self.media.stop(entity)

def zone_mask(include, exclude):
    def parse(value):
        try:
            zones = json.loads(value) if isinstance(value,str) else value
            return [z for z in zones[:20] if isinstance(z,list) and len(z)==4 and all(type(n) in (int,float) and 0<=n<=100 for n in z) and z[2]>0 and z[3]>0 and z[0]+z[2]<=100 and z[1]+z[3]<=100]
        except (TypeError,ValueError):
            return []
    inc, exc = parse(include), parse(exclude)
    def inside(x,y,z):
        return z[0]<=x<z[0]+z[2] and z[1]<=y<z[1]+z[3]
    return [i for i in range(14400) if (not inc or any(inside((i%160+.5)/1.6,(i//160+.5)/.9,z) for z in inc)) and not any(inside((i%160+.5)/1.6,(i//160+.5)/.9,z) for z in exc)]

def motion_bounds(previous,current,mask):
    if previous is None or len(previous)!=len(current):
        return None
    points = [i for i in mask if abs(previous[i]-current[i])>=25]
    if len(points)<12:
        return None
    xs,ys=[i%160 for i in points],[i//160 for i in points]
    return [min(xs)/1.6,min(ys)/.9,(max(xs)-min(xs)+1)/1.6,(max(ys)-min(ys)+1)/.9]
