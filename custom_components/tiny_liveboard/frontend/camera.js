export function cameraMetrics(report,previous=null){const rows=[...report.values()],v=rows.find(x=>x.type==="inbound-rtp"&&(x.kind==="video"||x.mediaType==="video"));if(!v)return null;const codec=rows.find(x=>x.id===v.codecId),dt=previous&&v.id===previous.id?(v.timestamp-previous.timestamp)/1000:0;return {id:v.id,timestamp:v.timestamp,bytes:v.bytesReceived,bitrate:dt>0&&v.bytesReceived>=previous.bytes?Math.round((v.bytesReceived-previous.bytes)*8/dt):null,fps:v.framesPerSecond??null,width:v.frameWidth??null,height:v.frameHeight??null,codec:codec?.mimeType??null,packetsLost:v.packetsLost??null,jitterMs:Number.isFinite(v.jitter)?Math.round(v.jitter*1000):null}}
export function cameraLayout(w,h,ratios,g=8){
 ratios=[0,1].map(i=>Number.isFinite(ratios?.[i])&&ratios[i]>0?ratios[i]:16/9);w=Math.max(0,Number(w)||0);h=Math.max(0,Number(h)||0);const width=Math.max(0,Math.min(w*.5,(h-3*g)/(1/ratios[0]+1/ratios[1])));
 const heights=ratios.map(r=>width/r);
 const top=(h-heights[0]-heights[1]-g)/2;
 return {width,cameras:heights.map((height,i)=>({width,height,top:top+(i?heights[0]+g:0)}))};
}
export function fallbackURL(value){const u=new URL(value);if(!["ws:","wss:"].includes(u.protocol)||u.username||u.password||!u.pathname.endsWith("/api/ws")||!u.searchParams.get("src"))throw Error("Invalid stream URL");u.protocol=u.protocol==="wss:"?"https:":"http:";u.pathname=u.pathname.replace(/\/ws$/,"/stream.mjpeg");return u.href}
export class CameraEngine {
 constructor(element,url,onResize){this.element=element;this.failures=0;this.video=element.querySelector("video");this.status=element.querySelector(".camera-status");this.url=url;this.onResize=onResize;this.ratio=16/9;this.closed=false;this.delay=1000;this.lastFrame=0;this.blocked=false;this.video.onplaying=()=>{if(this.closed||!this.pc)return;this.blocked=false;this.failures=0;this.status.textContent="LIVE"};this.watch=setInterval(()=>{if(this.closed||!this.pc)return;const t=this.video.currentTime;if(this.pc.connectionState==="connected"&&t===this.lastFrame&&!this.blocked){if(++this.stalls>=3)this.retry(this.pc)}else this.stalls=0;this.lastFrame=t},5000);this.metrics=null;this.statsTimer=setInterval(()=>{this.sampleStats();this.renderDiagnostics()},5000);this.stalls=0;this.video.onresize=()=>{if(this.video.videoWidth&&this.video.videoHeight){this.ratio=this.video.videoWidth/this.video.videoHeight;this.onResize()}}}
 connect(){
  if(this.closed||this.pc||this.retryTimer||this.fallback||this.mse)return;
  if(!this.url){this.status.textContent="Konfigurer go2rtc i Studio";return}
  let url;try{url=new URL(this.url);if(!["ws:","wss:"].includes(url.protocol)||url.username||url.password)throw Error();if(location.protocol==="https:"&&url.protocol!=="wss:")throw Error()}catch{this.status.textContent="Ugyldig WebSocket-adresse eller manglende TLS";return}
  this.status.textContent="Forbinder…";
  try{
   const pc=this.pc=new RTCPeerConnection();const ws=this.ws=new WebSocket(url);let candidates=[],remote=false;
   const send=(type,value)=>{if(ws.readyState===WebSocket.OPEN)ws.send(JSON.stringify({type,value}))};
   pc.addTransceiver("video",{direction:"recvonly"});
   pc.ontrack=e=>{if(this.pc!==pc)return;this.video.srcObject=e.streams[0]||new MediaStream([e.track]);this.status.textContent="Modtager stream…";this.video.play().catch(()=>{if(this.pc===pc){this.blocked=true;this.status.textContent="Afspilning blokeret"}});e.track.onended=()=>this.retry(pc)};
   pc.onicecandidate=e=>{if(e.candidate)send("webrtc/candidate",e.candidate.candidate)};
   pc.onconnectionstatechange=()=>{if(this.pc!==pc)return;if(pc.connectionState==="connected"){clearTimeout(this.timeout);clearTimeout(this.disconnectTimer);clearTimeout(this.retryTimer);this.retryTimer=null;this.delay=1000;if(!this.blocked)this.status.textContent=this.video.readyState>=2&&!this.video.paused?"LIVE":"Afventer videobillede…"}else if(pc.connectionState==="failed")this.retry(pc);else if(pc.connectionState==="disconnected"){clearTimeout(this.disconnectTimer);this.disconnectTimer=setTimeout(()=>{if(pc.connectionState==="disconnected")this.retry(pc)},5000)}};
   ws.onopen=async()=>{try{const offer=await pc.createOffer();await pc.setLocalDescription(offer);send("webrtc/offer",pc.localDescription.sdp)}catch{this.retry(pc)}};
   ws.onmessage=async e=>{if(this.pc!==pc)return;try{const msg=JSON.parse(e.data);if(msg.type==="webrtc/answer"){await pc.setRemoteDescription({type:"answer",sdp:msg.value});remote=true;for(const c of candidates)await pc.addIceCandidate(c);candidates=[]}else if(msg.type==="webrtc/candidate"&&msg.value){const c={candidate:msg.value,sdpMid:"0"};if(remote)await pc.addIceCandidate(c);else candidates.push(c)}else if(msg.type==="error")this.retry(pc)}catch{this.retry(pc)}};
   ws.onerror=()=>this.retry(pc);ws.onclose=()=>{if(pc.connectionState!=="connected")this.retry(pc)};
   this.timeout=setTimeout(()=>{if(pc.connectionState!=="connected")this.retry(pc)},15000);
  }catch{this.retry(this.pc)}
 }
 renderDiagnostics(){const panel=this.element.querySelector(".camera-metrics");if(!panel||panel.hidden)return;const m=this.metrics;panel.textContent=[this.status.textContent,"Transport: "+(this.mse?"MSE":this.fallback?"MJPEG":this.pc?"WebRTC":"Ingen"),"Opløsning: "+(this.video.videoWidth&&this.video.videoHeight?this.video.videoWidth+" × "+this.video.videoHeight:this.fallback?.naturalWidth?this.fallback.naturalWidth+" × "+this.fallback.naturalHeight:"—"),"FPS: "+(m?.fps??"—"),"Bitrate: "+(m?.bitrate!=null?Math.round(m.bitrate/1000)+" kbit/s":"—"),"Codec: "+(m?.codec??"—"),"Pakketab: "+(m?.packetsLost??"—"),"Jitter: "+(m?.jitterMs!=null?m.jitterMs+" ms":"—")].join("\n")}
 async sampleStats(){const pc=this.pc;if(!pc||this.closed||this.statsPending)return;this.statsPending=true;try{const report=await pc.getStats();if(this.pc!==pc||this.closed)return;this.metrics=cameraMetrics(report,this.metrics);const m=this.metrics;if(m)this.status.title=[m.width&&m.height?m.width+"×"+m.height:null,m.fps!=null?m.fps+" FPS":null,m.bitrate!=null?Math.round(m.bitrate/1000)+" kbit/s":null,m.codec,m.packetsLost!=null?"Tabte pakker: "+m.packetsLost:null,m.jitterMs!=null?"Jitter: "+m.jitterMs+" ms":null].filter(Boolean).join(" · ")}catch{}finally{this.statsPending=false}}
 retry(pc){if(this.closed||this.pc!==pc||this.retryTimer)return;this.status.textContent="Genopretter forbindelse…";this.retryTimer=setTimeout(()=>{this.retryTimer=null;this.cleanup();if(++this.failures>=3)this.startMSE();else this.connect()},this.delay);this.delay=Math.min(this.delay*2,30000)}
 startMSE(){
  if(this.closed)return;
  if(typeof MediaSource==="undefined"){this.startFallback();return}
  const codecs=["avc1.640029","avc1.4D4029","avc1.42E01E","hvc1.1.6.L153.B0"].filter(c=>MediaSource.isTypeSupported('video/mp4; codecs="'+c+'"'));
  if(!codecs.length){this.startFallback();return}
  const m=this.mse={queue:[],bytes:0,last:0,stalls:0};
  const fail=()=>{if(this.closed||this.mse!==m)return;this.cleanup();this.startFallback()};
  try{
   m.source=new MediaSource();m.url=URL.createObjectURL(m.source);this.video.src=m.url;this.status.textContent="Forbinder via MSE…";
   m.timer=setTimeout(fail,20000);m.retry=setTimeout(()=>{if(this.mse!==m)return;this.cleanup();this.failures=0;this.connect()},300000);
   const pump=()=>{if(this.mse!==m||!m.buffer||m.buffer.updating)return;try{const b=m.buffer;if(b.buffered.length&&this.video.currentTime-b.buffered.start(0)>30){b.remove(b.buffered.start(0),this.video.currentTime-10);return}if(m.queue.length){const chunk=m.queue.shift();m.bytes-=chunk.byteLength;b.appendBuffer(chunk)}}catch{fail()}};
   m.source.addEventListener("sourceopen",()=>{if(this.mse!==m)return;try{
    const ws=m.ws=new WebSocket(this.url);ws.binaryType="arraybuffer";
    ws.onopen=()=>ws.send(JSON.stringify({type:"mse",value:codecs.join(",")}));
    ws.onmessage=e=>{if(this.mse!==m)return;try{if(typeof e.data==="string"){const msg=JSON.parse(e.data);if(msg.type==="error")return fail();if(msg.type==="mse"&&!m.buffer){if(!MediaSource.isTypeSupported(msg.value))return fail();m.buffer=m.source.addSourceBuffer(msg.value);m.buffer.addEventListener("updateend",pump);m.buffer.addEventListener("error",fail);pump()}}else if(e.data instanceof ArrayBuffer){m.bytes+=e.data.byteLength;if(m.bytes>8*1024*1024)return fail();m.queue.push(e.data);pump()}}catch{fail()}};
    ws.onerror=fail;ws.onclose=fail;
   }catch{fail()}},{once:true});
   this.video.play().catch(()=>{if(this.mse===m)this.status.textContent="Afventer MSE-afspilning…"});
   m.watch=setInterval(()=>{if(this.mse!==m)return;const t=this.video.currentTime;if(t>m.last){clearTimeout(m.timer);m.stalls=0;this.status.textContent="LIVE · MSE"}else if(++m.stalls>=4)fail();m.last=t},5000);
  }catch{fail()}
 }
 startFallback(){if(this.closed)return;let url;try{url=fallbackURL(this.url)}catch{this.failures=0;this.connect();return}const img=document.createElement("img");this.fallback=img;img.alt="Kamerastream";img.style.cssText="position:absolute;inset:0;width:100%;height:100%;object-fit:contain";this.video.style.visibility="hidden";this.element.insertBefore(img,this.video);this.status.textContent="Forbinder via MJPEG…";const stop=()=>{if(this.fallback!==img||this.closed)return;this.cleanup();this.failures=0;this.connect()};img.onload=()=>{if(this.fallback!==img)return;clearTimeout(this.fallbackTimeout);if(img.naturalWidth&&img.naturalHeight){this.ratio=img.naturalWidth/img.naturalHeight;this.onResize()}this.status.textContent="LIVE · MJPEG"};img.onerror=stop;this.fallbackTimeout=setTimeout(stop,20000);this.fallbackRetry=setTimeout(stop,300000);img.src=url}
 cleanup(){const m=this.mse;this.mse=null;if(m){clearTimeout(m.timer);clearTimeout(m.retry);clearInterval(m.watch);if(m.ws){m.ws.onopen=null;m.ws.onmessage=null;m.ws.onerror=null;m.ws.onclose=null;m.ws.close()}this.video.removeAttribute("src");this.video.load();if(m.url)URL.revokeObjectURL(m.url)}clearTimeout(this.fallbackTimeout);clearTimeout(this.fallbackRetry);if(this.fallback){this.fallback.onload=null;this.fallback.onerror=null;this.fallback.removeAttribute("src");this.fallback.remove();this.fallback=null;this.video.style.visibility=""}this.metrics=null;this.status.title="";clearTimeout(this.timeout);clearTimeout(this.disconnectTimer);this.stalls=0;this.lastFrame=0;this.blocked=false;const ws=this.ws,pc=this.pc;this.ws=null;this.pc=null;if(ws){ws.onclose=null;ws.onerror=null;ws.onmessage=null;ws.onopen=null;ws.close()}if(pc){pc.onconnectionstatechange=null;pc.ontrack=null;pc.onicecandidate=null;pc.close()}this.video.srcObject=null}
 close(){this.closed=true;clearInterval(this.watch);clearInterval(this.statsTimer);clearTimeout(this.retryTimer);this.cleanup();this.video.onresize=null;this.video.onplaying=null}
}

export function streamURL(base,name){
 const url=new URL(base);
 if(!["http:","https:"].includes(url.protocol)||url.username||url.password||url.search||url.hash)throw new Error("Invalid go2rtc base URL");
 url.pathname=url.pathname.replace(/\/$/,"")+"/api/ws";
 url.protocol=url.protocol==="https:"?"wss:":"ws:";
 url.searchParams.set("src",name);
 return url.href;
}
export async function discoverStreams(base,fetcher=fetch){
 const url=new URL(streamURL(base,""));
 url.protocol=url.protocol==="wss:"?"https:":"http:";
 url.pathname=url.pathname.replace(/\/ws$/,"/streams");
 url.search="";
 const response=await fetcher(url.href,{signal:AbortSignal.timeout(10000),credentials:"omit",redirect:"error"});
 if(!response.ok)throw new Error("HTTP "+response.status);
 const data=await response.json();
 if(!data||Array.isArray(data)||typeof data!=="object")throw new Error("Invalid stream list");
 return Object.keys(data).sort((a,b)=>a.localeCompare(b));
}
