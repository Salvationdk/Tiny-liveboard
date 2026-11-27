export function cameraLayout(w,h,ratios,g=8){
 ratios=[0,1].map(i=>Number.isFinite(ratios?.[i])&&ratios[i]>0?ratios[i]:16/9);w=Math.max(0,Number(w)||0);h=Math.max(0,Number(h)||0);const width=Math.max(0,Math.min(w*.5,(h-3*g)/(1/ratios[0]+1/ratios[1])));
 const heights=ratios.map(r=>width/r);
 const top=(h-heights[0]-heights[1]-g)/2;
 return {width,cameras:heights.map((height,i)=>({width,height,top:top+(i?heights[0]+g:0)}))};
}
export class CameraEngine {
 constructor(element,url,onResize){this.video=element.querySelector("video");this.status=element.querySelector(".camera-status");this.url=url;this.onResize=onResize;this.ratio=16/9;this.closed=false;this.delay=1000;this.lastFrame=0;this.blocked=false;this.video.onplaying=()=>{if(this.closed||!this.pc)return;this.blocked=false;this.status.textContent="LIVE"};this.watch=setInterval(()=>{if(this.closed||!this.pc)return;const t=this.video.currentTime;if(this.pc.connectionState==="connected"&&t===this.lastFrame&&!this.blocked){if(++this.stalls>=3)this.retry(this.pc)}else this.stalls=0;this.lastFrame=t},5000);this.stalls=0;this.video.onresize=()=>{if(this.video.videoWidth&&this.video.videoHeight){this.ratio=this.video.videoWidth/this.video.videoHeight;this.onResize()}}}
 connect(){
  if(this.closed||this.pc||this.retryTimer)return;
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
 retry(pc){if(this.closed||this.pc!==pc||this.retryTimer)return;this.status.textContent="Genopretter forbindelse…";this.retryTimer=setTimeout(()=>{this.retryTimer=null;this.cleanup();this.connect()},this.delay);this.delay=Math.min(this.delay*2,30000)}
 cleanup(){clearTimeout(this.timeout);clearTimeout(this.disconnectTimer);this.stalls=0;this.lastFrame=0;this.blocked=false;const ws=this.ws,pc=this.pc;this.ws=null;this.pc=null;if(ws){ws.onclose=null;ws.onerror=null;ws.onmessage=null;ws.onopen=null;ws.close()}if(pc){pc.onconnectionstatechange=null;pc.ontrack=null;pc.onicecandidate=null;pc.close()}this.video.srcObject=null}
 close(){this.closed=true;clearInterval(this.watch);clearTimeout(this.retryTimer);this.cleanup();this.video.onresize=null;this.video.onplaying=null}
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
