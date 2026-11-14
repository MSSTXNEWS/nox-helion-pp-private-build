import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import {catalog} from "./catalog.mjs";
import {execute,IDS} from "./ops.mjs";
import {mountPack02} from "./panel.mjs";
const srt="1\n00:00:01,000 --> 00:00:02,000\nПривет\n\n2\n00:00:01,800 --> 00:00:03,000\nМир";
const inputs={
 media:srt,docs:"Hello World. Привет мир!\n\nHello World.",data:"name,count\nAlice,2\nBob,3\nAlice,2",
 dev:"hello",workflow:"- [x] Сделано | owner=1 | weight=3 | minutes=30\n- [ ] Делаем | owner=2 | weight=1 | minutes=20 | status=doing"
};
const overrides={
 "media.transcript.speakers":"Anna: Привет\nBob: Hello\nAnna: Мир",
 "data.csv.stringify":'[{"name":"Alice","age":3}]',
 "data.json.pretty":'{"a":1}',"data.json.flatten":'{"a":{"b":2}}',"data.json.keys":'{"a":1}',
 "dev.json.compare":'{"a":1}',"dev.json.validate":'{"a":1}',
 "dev.url.inspect":"https://example.org:443/path?x=1",
 "dev.url.query_encode":'{"q":"привет","x":2}',"dev.url.query_decode":"q=hi&x=2",
 "dev.base64.decode":"0J/RgNC40LLQtdGC","dev.hex.decode":"d09fd180d0b8d0b2d0b5d182",
 "workflow.receipt.inspect":'{"run_id":"R-123","sha256":"'+("a".repeat(64))+'"}',
 "workflow.manifest.compare":'{"a":1}',"workflow.runid.validate":"NOX-R02-20261028"
};
const options={
 "media.subtitles.shift":{seconds:2},"media.subtitles.search":{term:"Привет"},
 "docs.text.chunks":{size:100},"data.csv.select":{fields:"name"},
 "data.csv.filter":{field:"name",term:"Alice"},
 "data.csv.sort":{field:"count",desc:true},
 "dev.diff.lines":{compare:"bye"},"dev.json.compare":{compare:'{"a":2}'},
 "workflow.manifest.compare":{compare:'{"a":2,"b":2}'}
};
const inputFor=id=>overrides[id]??inputs[id.split(".")[0]];
test("exactly 50 task-backed operations, distinct from PACK01",()=>{
 assert.equal(IDS.length,50);assert.equal(catalog.actions.length,50);
 assert.equal(new Set(IDS).size,50);
 assert.deepEqual(IDS,catalog.actions.map(x=>x.routeId));
 assert.equal(catalog.actions.filter(x=>x.exeIntegrated).length,0);
 const first=JSON.parse(fs.readFileSync(new URL("../NOX-PACK01-50/catalog.json",import.meta.url),"utf8"));
 assert.equal(first.actions.length,50);
 for(const x of first.actions)assert.ok(!IDS.includes(x.routeId),x.routeId);
});
for(const item of catalog.actions){
 test(item.taskId+" "+item.routeId+" executes offline",()=>{
  const out=execute(item.routeId,inputFor(item.routeId),options[item.routeId]??{});
  assert.equal(out.id,item.routeId);assert.equal(out.status,"OK");
  assert.ok(out.result!==undefined);
 });
}
test("media conversions and real timing math",()=>{
 assert.ok(execute("media.srt.to_vtt",srt).result.startsWith("WEBVTT"));
 assert.equal(execute("media.subtitles.duration",srt).result,2.2);
 assert.equal(execute("media.subtitles.overlaps",srt).result.length,1);
 assert.ok(execute("media.subtitles.shift",srt,{seconds:1}).result.includes("00:00:02,000"));
});
test("CSV quoting and numeric priority",()=>{
 const parsed=execute("data.csv.parse",'id,note\n1,"hello, ""world"""').result;
 assert.equal(parsed[0].note,'hello, "world"');
 assert.equal(execute("workflow.progress.weighted",inputs.workflow).result.weightedPercent,75);
});
test("strict input protection / no foreign handler",()=>{
 assert.throws(()=>execute("system.pc_control","x"),/UNKNOWN_FUNCTION/);
 assert.throws(()=>execute("docs.words.count","a".repeat(100001)),/INPUT_SIZE/);
 assert.throws(()=>execute("dev.url.inspect","file:///etc/passwd"),/HTTP_ONLY/);
 assert.throws(()=>mountPack02(null),/APPROVED_SECONDARY_MOUNT_REQUIRED/);
});
