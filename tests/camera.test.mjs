import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
const source=await readFile(new URL("../custom_components/tiny_liveboard/frontend/camera.js",import.meta.url),"utf8");
const {cameraLayout}=await import("data:text/javascript;base64,"+Buffer.from(source).toString("base64"));
for(const ratios of [[16/9,16/9],[4/3,21/9],[9/16,16/9]]){const l=cameraLayout(1920,1028,ratios);for(let i=0;i<2;i++)assert.ok(Math.abs(l.cameras[i].width/l.cameras[i].height-ratios[i])<1e-9);assert.ok(l.cameras[0].top>=0);assert.ok(l.cameras[1].top+l.cameras[1].height<=1028);assert.ok(l.cameras[0].top+l.cameras[0].height<=l.cameras[1].top)}

const {streamURL,discoverStreams}=await import("data:text/javascript;base64,"+Buffer.from(source).toString("base64"));
assert.equal(streamURL("http://localhost:1984","front garden"),"ws://localhost:1984/api/ws?src=front+garden");
assert.equal(streamURL("https://example.org/proxy/","a&b"),"wss://example.org/proxy/api/ws?src=a%26b");
assert.throws(()=>streamURL("http://user:pass@localhost","x"));
assert.deepEqual(await discoverStreams("http://localhost:1984",async url=>{assert.equal(url,"http://localhost:1984/api/streams");return {ok:true,json:async()=>({z:{},a:{}})}}),["a","z"]);

for(const ratios of [[0,NaN],[],[Infinity,-1]]){const l=cameraLayout(1920,1080,ratios);assert.ok(l.cameras.every(c=>Number.isFinite(c.height)&&c.height>0))}
await assert.rejects(discoverStreams("http://localhost:1984",async()=>({ok:false,status:503})),/503/);
await assert.rejects(discoverStreams("http://localhost:1984",async()=>({ok:true,json:async()=>[]})),/Invalid/);

const {cameraMetrics}=await import("data:text/javascript;base64,"+Buffer.from(source).toString("base64"));
const report=(timestamp,bytesReceived)=>new Map([["v",{id:"v",type:"inbound-rtp",kind:"video",timestamp,bytesReceived,codecId:"c",framesPerSecond:25,frameWidth:1920,frameHeight:1080,jitter:.012,packetsLost:3}],["c",{id:"c",mimeType:"video/H264"}]]);
const first=cameraMetrics(report(1000,1000));
assert.equal(first.bitrate,null);
const second=cameraMetrics(report(2000,126000),first);
assert.equal(second.bitrate,1000000);
assert.equal(second.codec,"video/H264");
assert.equal(second.jitterMs,12);
assert.equal(cameraMetrics(report(3000,0),second).bitrate,null);
assert.equal(cameraMetrics(new Map()),null);
