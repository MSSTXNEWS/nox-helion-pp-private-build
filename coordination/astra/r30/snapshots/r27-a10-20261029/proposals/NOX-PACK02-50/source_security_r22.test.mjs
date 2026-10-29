/* NOX V16 R22 — source-only regression of the EXISTING PACK02 50 operators.
 * Run: node --test proposals/NOX-PACK02-50/source_security_r22.test.mjs
 * No EXE, NSIS, LLM, network requests, Windows runtime, or source integration.
 */
import test from "node:test";
import assert from "node:assert/strict";
import {execute,IDS} from "./ops.mjs";
import {catalog} from "./catalog.mjs";

const run=(id,input,options={})=>execute(id,input,options).result;
const mustReject=(id,input,error,options={})=>
  assert.throws(()=>run(id,input,options),new RegExp(error));

test("R22: all original 50 TaskIDs/functions remain in canonical order",()=>{
  assert.equal(IDS.length,50);
  assert.deepEqual(IDS,catalog.actions.map(x=>x.routeId));
  assert.equal(new Set(IDS).size,50);
});
test("R22 CSV: normal escaped quotes remain intact",()=>{
  assert.equal(run("data.csv.parse",'name,note\nA,"hello, ""world"""')[0].note,'hello, "world"');
});
test("R22 CSV: multiline quoted text remains a single cell",()=>{
  assert.equal(run("data.csv.parse",'name,note\nA,"a\nb"')[0].note,"a\nb");
});
test("R22 CSV: CRLF and trailing newline work",()=>{
  assert.deepEqual(run("data.csv.parse","name,count\r\nAda,1\r\n"),[{name:"Ada",count:"1"}]);
});
test("R22 CSV: literal comma outside quotation is a field separator",()=>{
  assert.deepEqual(run("data.csv.parse","a,b\n1,2"),[{a:"1",b:"2"}]);
});
test("R22 CSV: reject embedded quote in unquoted value",()=>{
  mustReject("data.csv.parse",'a,b\n1,ab"c',"BAD_CSV_QUOTE");
});
test("R22 CSV: reject trailing bytes after closing quote",()=>{
  mustReject("data.csv.parse",'a,b\n1,"ok"junk',"BAD_CSV_QUOTE");
});
test("R22 CSV: reject unterminated quoted field",()=>{
  mustReject("data.csv.parse",'a,b\n1,"unfinished',"BAD_CSV_QUOTE");
});
test("R22 CSV: reject case-equivalent column names",()=>{
  mustReject("data.csv.parse","Owner,owner\nAlice,Bob","INVALID_CSV_HEADER");
});
test("R22 CSV: reject NFC-equivalent column names",()=>{
  mustReject("data.csv.parse","naïve,nai\u0308ve\nA,B","INVALID_CSV_HEADER");
});
test("R22 CSV: reject wrong data row width",()=>{
  mustReject("data.csv.parse","one,two\nvalue","CSV_WIDTH_MISMATCH");
});
test("R22 CSV: quoted empty cell remains empty",()=>{
  assert.equal(run("data.csv.parse",'a,b\n1,""')[0].b,"");
});
test("R22 CSV: downstream sort/filter retains correct columns",()=>{
  const csv="name,score\nAlice,2\nBob,10";
  assert.equal(run("data.csv.sort",csv,{field:"score",desc:true})[0].name,"Bob");
  assert.equal(run("data.csv.filter",csv,{field:"name",term:"Bob"})[0].score,"10");
});
test("R22 JSON: normal nested dotted path remains compatible",()=>{
  assert.deepEqual(run("data.json.flatten",'{"a":{"b":2},"x":false}'),{"a.b":2,x:false});
});
test("R22 JSON: literal dotted key cannot overwrite nested path",()=>{
  const out=run("data.json.flatten",'{"a.b":1,"a":{"b":2}}');
  assert.equal(out["a\\.b"],1);
  assert.equal(out["a.b"],2);
});
test("R22 JSON: backslash in key is encoded distinctly",()=>{
  const out=run("data.json.flatten",'{"a\\\\b":1,"a":{"b":2}}');
  assert.equal(out["a\\\\b"],1);
  assert.equal(out["a.b"],2);
});
test("R22 JSON: __proto__ cannot mutate output prototype",()=>{
  const out=run("data.json.flatten",'{"__proto__":5,"constructor":2}');
  assert.equal(Object.getPrototypeOf(out),Object.prototype);
  assert.equal(Object.getOwnPropertyDescriptor(out,"__proto__").value,5);
  assert.equal(out.constructor,2);
});
test("R22 JSON: preserve otherwise lost empty object and array",()=>{
  const out=run("data.json.flatten",'{"empty":[],"obj":{}}');
  assert.deepEqual(out,{empty:[],obj:{}});
});
test("R22 JSON: comparisons correctly distinguish colliding names",()=>{
  const out=run("dev.json.compare",'{"a.b":1,"a":{"b":2}}',{
    compare:'{"a.b":4,"a":{"b":2}}'
  });
  assert.deepEqual(out,[{path:"a\\.b",before:1,after:4}]);
});
test("R22 JSON: original weighted progress algorithm unchanged",()=>{
  const t="- [x] Done | weight=3\n- [ ] Next | weight=1";
  assert.deepEqual(run("workflow.progress.weighted",t),
    {weightedPercent:75,completed:1,total:2});
});
test("R22 URL: normal query decode remains compatible",()=>{
  assert.deepEqual(run("dev.url.query_decode","x=1&name=Anna"),{x:"1",name:"Anna"});
});
test("R22 URL: reject exact duplicate query property",()=>{
  mustReject("dev.url.query_decode","x=1&x=2","DUPLICATE_QUERY_KEY");
});
test("R22 URL: reject casefold duplicate query property",()=>{
  mustReject("dev.url.query_decode","Owner=1&owner=2","DUPLICATE_QUERY_KEY");
});
test("R22 URL: reject NFC-equivalent query property",()=>{
  mustReject("dev.url.query_decode","na%C3%AFve=1&nai%CC%88ve=2","DUPLICATE_QUERY_KEY");
});
test("R22 URL: __proto__ query key is data, never prototype mutation",()=>{
  const out=run("dev.url.query_decode","__proto__=7");
  assert.equal(Object.getPrototypeOf(out),Object.prototype);
  assert.equal(Object.getOwnPropertyDescriptor(out,"__proto__").value,"7");
});
test("R22: no privileged route can be dispatched via PACK02",()=>{
  mustReject("system.pc_control","x","UNKNOWN_FUNCTION");
  mustReject("docs.words.count","x".repeat(100001),"INPUT_SIZE");
});
