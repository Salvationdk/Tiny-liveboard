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

const {dailyRows}=await import("data:text/javascript;base64,"+Buffer.from(source).toString("base64"));
assert.equal(forecastRows([{datetime:"2026-01-01T00:00:00Z"},{datetime:"2026-01-01T01:00:00+01:00"}],Date.parse("2026-01-01T00:00:00Z")).length,1);
assert.equal(dailyRows([{datetime:"2026-01-01T23:00:00Z"},{datetime:"2026-01-02T23:00:00Z"}],Date.parse("2026-01-02T12:00:00Z"),"Europe/Copenhagen").length,2);

const {weatherTime}=await import("data:text/javascript;base64,"+Buffer.from(source).toString("base64"));
assert.equal(weatherTime("2026-07-01T12:00:00Z","Europe/Copenhagen"),weatherTime("2026-07-01T14:00:00Z","UTC"));
assert.equal(advice([{temperature:10}],{}).find(x=>x[0]==="Bilruder")[1],"Ukendt");
assert.equal(advice([],{}).find(x=>x[0]==="Nedbør")[1],"Ingen nedbørsdata");

const {localAlerts}=await import("data:text/javascript;base64,"+Buffer.from(source).toString("base64"));
const alerts=localAlerts([{title:"Local",bounds:[55,10,56,12]},{title:"Other",bounds:[57,10,58,12]},{title:"Unknown"},{title:"Expired",bounds:[55,10,56,12],expires:"2020-01-01"}],55.7,11.1,Date.parse("2026-01-01"));
assert.deepEqual(alerts.local.map(a=>a.title),["Local"]);
assert.deepEqual(alerts.unknown.map(a=>a.title),["Unknown"]);
