import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
const source=await readFile(new URL("../custom_components/tiny_liveboard/frontend/weather.js",import.meta.url),"utf8");
const {forecastRows,graphPoints}=await import("data:text/javascript;base64,"+Buffer.from(source).toString("base64"));
assert.equal(forecastRows([{datetime:"bad"},{datetime:"2026-01-01T00:00:00Z"}],Date.parse("2026-01-01T00:00:00Z")).length,1);
assert.deepEqual(graphPoints([{temperature:null}],"temperature"),[]);
assert.equal(graphPoints([{temperature:0},{temperature:5}],"temperature").length,2);
assert.ok(graphPoints([{temperature:0}],"temperature").flat().every(Number.isFinite));
