"""Administrator-controlled local camera media capture."""
import asyncio
import shutil
import time
import re
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
from homeassistant.components.camera import async_get_image
from homeassistant.components.camera import async_get_stream_source

class MediaEngine:
    def __init__(self, hass):
        self.hass = hass
        self.root = Path("/media/tiny_liveboard")
        self.jobs = {}
        self.started = {}
        self.lock = asyncio.Lock()

    def destination(self, entity, kind, suffix):
        folder = self.root / kind
        folder.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(folder).free < 512 * 1024**2:
            raise ValueError("Insufficient free disk space")
        name = entity.replace(".", "_") + "_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:8]
        return folder / (name + suffix)

    async def snapshot(self, entity):
        image = await async_get_image(self.hass, entity)
        suffix = ".png" if image.content_type == "image/png" else ".jpg"
        path = await self.hass.async_add_executor_job(self.destination, entity, "snapshots", suffix)
        await self.hass.async_add_executor_job(path.write_bytes, image.content)
        return {"file": path.name}

    async def start(self, entity, minutes):
        async with self.lock:
            if entity in self.jobs:
                raise ValueError("Camera already recording")
            if len(self.jobs) >= 2:
                raise ValueError("Maximum two recordings")
            source = await async_get_stream_source(self.hass, entity)
            if not source:
                raise ValueError("Camera has no server-side stream source")
            ffmpeg = await self.hass.async_add_executor_job(shutil.which, "ffmpeg")
            if not ffmpeg:
                raise ValueError("FFmpeg unavailable")
            path = await self.hass.async_add_executor_job(self.destination, entity, "recordings", ".mp4")
            proc = await asyncio.create_subprocess_exec(ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-i", source, "-map", "0:v:0", "-c:v", "copy", "-an", "-t", str(minutes*60), "-fs", str(512*1024**2), "-movflags", "+frag_keyframe+empty_moov", str(path), stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            self.jobs[entity] = (proc, path)
            self.started[entity] = time.monotonic()
            self.hass.async_create_task(self.watch(entity, proc, path))
            return {"recording": True, "file": path.name}

    async def watch(self, entity, proc, path):
        await proc.wait()
        async with self.lock:
            if self.jobs.get(entity, (None,))[0] is proc:
                self.jobs.pop(entity, None)
                self.started.pop(entity, None)

    async def stop(self, entity):
        async with self.lock:
            job = self.jobs.get(entity)
            if not job:
                return {"recording": False}
            proc, path = job
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), 10)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
            self.jobs.pop(entity, None)
            return {"recording": False, "file": path.name}

    async def close(self):
        for entity in list(self.jobs):
            await self.stop(entity)

    def list_files(self):
        active = {path.name for _, path in self.jobs.values()}
        result = []
        for kind in ("snapshots", "recordings"):
            folder = self.root / kind
            if not folder.exists():
                continue
            for path in folder.iterdir():
                if path.is_symlink() or not path.is_file() or path.suffix not in (".jpg", ".png", ".mp4") or path.name in active:
                    continue
                stat = path.stat()
                result.append({"kind": kind, "file": path.name, "size": stat.st_size, "modified": stat.st_mtime})
        return {"items": sorted(result, key=lambda x: x["modified"], reverse=True)[:500], "bytes": sum(x["size"] for x in result)}

    def delete_file(self, kind, name):
        if kind not in ("snapshots", "recordings") or not re.fullmatch(r"[a-zA-Z0-9_]+\.(jpg|png|mp4)", name):
            raise ValueError("Invalid media file")
        if any(path.name == name for _, path in self.jobs.values()):
            raise ValueError("Recording active")
        path = self.root / kind / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("Media unavailable")
        path.unlink()

    def cleanup(self, days):
        cutoff = time.time() - days * 86400
        count = 0
        for item in self.list_files()["items"]:
            if item["modified"] < cutoff:
                self.delete_file(item["kind"], item["file"])
                count += 1
        return count
