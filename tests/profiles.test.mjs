import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
const source=readFileSync(new URL("../custom_components/tiny_liveboard/frontend/display.js",import.meta.url),"utf8");
const helpers=source.slice(source.indexOf("export function resolveProfile"),source.indexOf("class TinyLiveboard extends"));
const {scheduledProfile,resolveProfile}=await import("data:text/javascript;base64,"+Buffer.from(helpers).toString("base64"));
const base={screens:{kitchen:"Day"},profiles:{Day:{news:"day"},Night:{news:"night"}},schedules:[{screen:"kitchen",profile:"Night",days:[1],start:"22:00",end:"07:00"}],_revision:4};
const pick=t=>scheduledProfile(base,"kitchen",new Date(t),"Europe/Copenhagen");
test("overnight schedule uses previous weekday after midnight",()=>{
 assert.equal(pick("2026-11-23T21:00:00Z"),"Night");
 assert.equal(pick("2026-11-24T05:59:00Z"),"Night");
 assert.equal(pick("2026-11-24T06:00:00Z"),"Day");
});
test("schedule does not affect other screens",()=>assert.equal(scheduledProfile(base,"other",new Date("2026-11-23T22:00:00Z")),""));
test("profile preserves central revision",()=>assert.equal(resolveProfile(base,"Night")._revision,4));
test("unknown profile returns base",()=>assert.equal(resolveProfile(base,"constructor"),base));
test("invalid timezone falls back",()=>assert.equal(scheduledProfile(base,"kitchen",new Date(),"invalid"),"Day"));
