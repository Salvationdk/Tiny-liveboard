import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
const source=await readFile(new URL("../custom_components/tiny_liveboard/frontend/camera.js",import.meta.url),"utf8");
const {cameraLayout}=await import("data:text/javascript;base64,"+Buffer.from(source).toString("base64"));
for(const ratios of [[16/9,16/9],[4/3,21/9],[9/16,16/9]]){const l=cameraLayout(1920,1028,ratios);for(let i=0;i<2;i++)assert.ok(Math.abs(l.cameras[i].width/l.cameras[i].height-ratios[i])<1e-9);assert.ok(l.cameras[0].top>=0);assert.ok(l.cameras[1].top+l.cameras[1].height<=1028);assert.ok(l.cameras[0].top+l.cameras[0].height<=l.cameras[1].top)}
