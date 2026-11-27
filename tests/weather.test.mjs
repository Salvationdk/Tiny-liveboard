import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
const source=await readFile(new URL("../custom_components/tiny_liveboard/frontend/weather.js",import.meta.url),"utf8");
const {forecastRows,graphPoints}=await import("data:text/javascript;base64,"+Buffer.from(source).toString("base64"));
assert.equal(forecastRows([{datetime:"bad"},{datetime:"2026-01-01T00:00:00Z"}],Date.parse("2026-01-01T00:00:00Z")).length,1);
assert.deepEqual(graphPoints([{temperature:null}],"temperature"),[]);
assert.equal(graphPoints([{temperature:0},{temperature:5}],"temperature").length,2);
assert.ok(graphPoints([{temperature:0}],"temperature").flat().every(Number.isFinite));

const {moon,advice}=await import("data:text/javascript;base64,"+Buffer.from(source).toString("base64"));
assert.equal(moon(new Date("2000-01-06T18:14:00Z")).phase,"Nymåne");
assert.equal(advice([],{}).find(x=>x[0]==="Bilruder")[1],"Ukendt");

const {solar,tilePosition}=await import("data:text/javascript;base64,"+Buffer.from(source).toString("base64"));
assert.equal(solar(new Date(),100,0),null);
assert.ok(solar(new Date("2026-06-21"),55.7,11.1).minutes>900);
assert.deepEqual(tilePosition(0,0,2),{x:2,y:2});
