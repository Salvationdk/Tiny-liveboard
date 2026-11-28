"""Administrator-controlled local camera media capture."""
import asyncio
import shutil
import time
import re
import threading
import tempfile
import logging
_LOGGER = logging.getLogger(__name__)
from urllib.parse import urlsplit
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
async def async_get_image(hass, entity):
    from homeassistant.components.camera import async_get_image as capture
    return await capture(hass, entity)
async def async_get_stream_source(hass, entity):
    from homeassistant.components.camera import async_get_stream_source as resolve
    return await resolve(hass, entity)

class MediaEngine:
    def __init__(self, hass):
        self.hass = hass
        self.root = Path("/media/tiny_liveboard")
        self.jobs = {}
        self.buffers = {}
        self.started = {}
        self.finalizing = set()
        self.file_lock = threading.RLock()
        self.lock = asyncio.Lock()

    def destination(self, entity, kind, suffix):
        folder = self.root / kind
        folder.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(folder).free < 512 * 1024**2:
            raise ValueError("Insufficient free disk space")
        name = entity.replace(".", "_") + "_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:8]
        return folder / (name + suffix)

    async def snapshot(self, entity, source=None):
        if source:
            ffmpeg = await self.hass.async_add_executor_job(shutil.which, 'ffmpeg')
            if not ffmpeg:
                raise ValueError('FFmpeg unavailable')
            path = await self.hass.async_add_executor_job(self.destination, entity, 'snapshots', '.jpg')
            proc = await asyncio.create_subprocess_exec(ffmpeg, '-nostdin', '-loglevel', 'error', '-i', source, '-frames:v', '1', str(path), stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            try:
                await asyncio.wait_for(proc.wait(), 20)
                if proc.returncode:
                    raise ValueError('Snapshot failed')
                return {'file': path.name}
            finally:
                if proc.returncode is None:
                    proc.kill()
                    await proc.wait()
                if proc.returncode:
                    await self.hass.async_add_executor_job(lambda: path.unlink(missing_ok=True))
        image = await async_get_image(self.hass, entity)
        suffix = ".png" if image.content_type == "image/png" else ".jpg"
        path = await self.hass.async_add_executor_job(self.destination, entity, "snapshots", suffix)
        await self.hass.async_add_executor_job(path.write_bytes, image.content)
        return {"file": path.name}

    async def start(self, entity, minutes, source_override=None):
        async with self.lock:
            if entity in self.jobs:
                raise ValueError("Camera already recording")
            if len(self.jobs) >= 2:
                raise ValueError("Maximum two recordings")
            source = source_override or await async_get_stream_source(self.hass, entity)
            if not source:
                raise ValueError("Camera has no server-side stream source")
            ffmpeg = await self.hass.async_add_executor_job(shutil.which, "ffmpeg")
            if not ffmpeg:
                raise ValueError("FFmpeg unavailable")
            path = await self.hass.async_add_executor_job(self.destination, entity, "recordings", ".mp4")
            proc = await asyncio.create_subprocess_exec(ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-i", source, "-map", "0:v:0", "-c:v", "copy", "-an", "-t", str(minutes*60), "-fs", str(512*1024**2), "-movflags", "+frag_keyframe+empty_moov", str(path), stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            self.jobs[entity] = (proc, path)
            try:
                await self.save_preroll(entity, path)
            except Exception:
                _LOGGER.warning('Pre-recording export failed; keeping main recording', exc_info=True)
            self.started[entity] = time.monotonic()
            self.hass.async_create_task(self.watch(entity, proc, path))
            return {"recording": True, "file": path.name}

    async def watch(self, entity, proc, path):
        await proc.wait()
        async with self.lock:
            if self.jobs.get(entity, (None,))[0] is proc:
                await self.merge_preroll(path)
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
            await self.merge_preroll(path)
            self.jobs.pop(entity, None)
            self.started.pop(entity, None)
            return {"recording": False, "file": path.name}

    async def close(self):
        for entity in list(self.buffers):
            await self.stop_buffer(entity)
        for entity in list(self.jobs):
            await self.stop(entity)

    def list_files(self, limit=500):
        active = {path.name for _, path in self.jobs.values()}
        active |= {Path(name).stem+'_pre.mp4' for name in active}
        active |= self.finalizing
        result = []
        for kind in ("snapshots", "recordings"):
            folder = self.root / kind
            if not folder.exists():
                continue
            for path in folder.iterdir():
                if path.is_symlink() or not path.is_file() or path.suffix not in (".jpg", ".png", ".mp4") or path.name in active:
                    continue
                stat = path.stat()
                result.append({"kind": kind, "file": path.name, "size": stat.st_size, "modified": stat.st_mtime, "locked": path.with_suffix(path.suffix + ".lock").is_file()})
        return {"items": sorted(result, key=lambda x: x["modified"], reverse=True)[:limit], "bytes": sum(x["size"] for x in result)}

    def delete_file(self, kind, name):
        with self.file_lock:
            self._delete_file(kind, name)

    def _delete_file(self, kind, name):
        if kind not in ("snapshots", "recordings") or not re.fullmatch(r"[a-zA-Z0-9_]+\.(jpg|png|mp4)", name):
            raise ValueError("Invalid media file")
        if name in self.finalizing or any(name in (path.name,path.stem+'_pre.mp4') for _, path in self.jobs.values()):
            raise ValueError("Recording active")
        path = self.root / kind / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("Media unavailable")
        if path.with_suffix(path.suffix + ".lock").exists():
            raise ValueError("Media is locked")
        path.unlink()

    def cleanup(self, days):
        cutoff = time.time() - days * 86400
        count = 0
        for item in self.list_files(None)["items"]:
            if item["modified"] < cutoff and not item["locked"]:
                try:
                    self.delete_file(item["kind"], item["file"])
                    count += 1
                except (ValueError, FileNotFoundError):
                    continue
        return count

    def set_locked(self, kind, name, locked):
        with self.file_lock:
            if kind not in ("snapshots", "recordings") or not re.fullmatch(r"[a-zA-Z0-9_]+\.(jpg|png|mp4)", name):
                raise ValueError("Invalid media file")
            path = self.root / kind / name
            if path.is_symlink() or not path.is_file():
                raise ValueError("Media unavailable")
            marker = path.with_suffix(path.suffix + ".lock")
            if locked:
                marker.touch(exist_ok=True)
            else:
                marker.unlink(missing_ok=True)
            return {"locked": locked}

    async def start_buffer(self, entity, seconds):
        await self.stop_buffer(entity)
        if not seconds:
            return
        source = await async_get_stream_source(self.hass, entity)
        ffmpeg = await self.hass.async_add_executor_job(shutil.which, "ffmpeg")
        if not source or not ffmpeg:
            raise ValueError("Buffer source unavailable")
        folder = tempfile.TemporaryDirectory(prefix="tiny-motion-")
        try:
            proc = await asyncio.create_subprocess_exec(ffmpeg,"-nostdin","-loglevel","error","-i",source,"-map","0:v:0","-an","-vf","scale=640:-2","-c:v","libx264","-preset","ultrafast","-b:v","600k","-maxrate","800k","-bufsize","800k","-force_key_frames","expr:gte(t,n_forced*2)","-f","hls","-hls_time","2","-hls_list_size",str((seconds+1)//2),"-hls_flags","delete_segments+omit_endlist","-hls_segment_filename",folder.name+"/part%09d.ts",folder.name+"/index.m3u8",stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
        except BaseException:
            folder.cleanup()
            raise
        self.buffers[entity]=(proc,folder,seconds)

    async def stop_buffer(self, entity):
        job=self.buffers.pop(entity,None)
        if not job:
            return
        proc,folder,_=job
        if proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()
        await self.hass.async_add_executor_job(folder.cleanup)

    async def save_preroll(self, entity, recording):
        job=self.buffers.get(entity)
        if not job:
            return
        proc,folder,seconds=job
        if proc.returncode is not None:
            return
        def collect():
            root=Path(folder.name)
            try:
                names=[line.strip() for line in (root/"index.m3u8").read_text().splitlines() if re.fullmatch(r"part[0-9]+\.ts",line.strip())]
                return b"".join((root/name).read_bytes() for name in names[-((seconds+1)//2):])
            except OSError:
                return b""
        data=await self.hass.async_add_executor_job(collect)
        if not data or len(data)>16*1024**2:
            return
        ffmpeg=await self.hass.async_add_executor_job(shutil.which,"ffmpeg")
        if not ffmpeg:
            return
        target=recording.with_name(recording.stem+"_pre.mp4")
        worker=await asyncio.create_subprocess_exec(ffmpeg,"-nostdin","-loglevel","error","-f","mpegts","-i","pipe:0","-c","copy","-movflags","+faststart",str(target),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
        try:
            await asyncio.wait_for(worker.communicate(data),15)
        finally:
            if worker.returncode is None:
                worker.kill()
                await worker.wait()
            if worker.returncode:
                await self.hass.async_add_executor_job(lambda:target.unlink(missing_ok=True))

    async def merge_preroll(self, path):
        pre = path.with_name(path.stem+"_pre.mp4")
        tmp = path.with_name(path.stem+"_merge.tmp")
        self.finalizing.update((path.name,pre.name))
        worker = None
        try:
            def ready():
                return all(p.is_file() and not p.is_symlink() and p.stat().st_size > 0 for p in (pre,path)) and shutil.disk_usage(path.parent).free > 512*1024**2 and not any(p.with_suffix(p.suffix+".lock").exists() for p in (pre,path))
            if not await self.hass.async_add_executor_job(ready):
                return
            ffmpeg = await self.hass.async_add_executor_job(shutil.which,"ffmpeg")
            if not ffmpeg:
                return
            # Normalize dimensions, sample aspect ratio, frame rate and timestamps.
            graph = "[0:v]scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=25,setpts=PTS-STARTPTS[a];[1:v]scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=25,setpts=PTS-STARTPTS[b];[a][b]concat=n=2:v=1:a=0[out]"
            worker = await asyncio.create_subprocess_exec(ffmpeg,"-nostdin","-loglevel","error","-y","-i",str(pre),"-i",str(path),"-filter_complex",graph,"-map","[out]","-c:v","libx264","-preset","ultrafast","-crf","23","-threads","2","-pix_fmt","yuv420p","-movflags","+faststart","-f","mp4",str(tmp),stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
            await asyncio.wait_for(worker.wait(),900)
            if worker.returncode:
                raise ValueError("FFmpeg merge failed")
            def commit():
                with self.file_lock:
                    if not tmp.is_file() or tmp.stat().st_size == 0 or any(p.with_suffix(p.suffix+".lock").exists() for p in (pre,path)):
                        return
                    tmp.replace(path)
                    pre.unlink(missing_ok=True)
            await self.hass.async_add_executor_job(commit)
        except Exception:
            _LOGGER.warning("Recording merge failed; retaining original clips",exc_info=True)
        finally:
            if worker is not None and worker.returncode is None:
                try:
                    worker.kill()
                except ProcessLookupError:
                    pass
                await worker.wait()
            await self.hass.async_add_executor_job(lambda:tmp.unlink(missing_ok=True))
            self.finalizing.difference_update((path.name,pre.name))

    async def thumbnail(self, name):
        if not re.fullmatch(r"[a-zA-Z0-9_]+\.mp4", name):
            raise ValueError("Invalid recording")
        source = self.root / "recordings" / name
        if source.is_symlink() or not source.is_file() or any(p == source for _,p in self.jobs.values()):
            raise ValueError("Recording unavailable")
        ffmpeg = await self.hass.async_add_executor_job(shutil.which,"ffmpeg")
        if not ffmpeg:
            raise ValueError("FFmpeg unavailable")
        proc = await asyncio.create_subprocess_exec(ffmpeg,"-nostdin","-loglevel","error","-i",str(source),"-frames:v","1","-vf","scale=320:-2","-f","image2pipe","-vcodec","mjpeg","pipe:1",stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
        try:
            output,_ = await asyncio.wait_for(proc.communicate(),15)
            if proc.returncode or not output or len(output)>512*1024:
                raise ValueError("Thumbnail unavailable")
            import base64
            return {"image":"data:image/jpeg;base64,"+base64.b64encode(output).decode("ascii")}
        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()

def configured_stream(cfg, slot):
    value = cfg.get("captureRtsp"+str(slot),"")
    if not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in ("rtsp","rtsps") or not parsed.hostname or len(value)>2048:
        raise ValueError("Invalid configured RTSP stream")
    return value
