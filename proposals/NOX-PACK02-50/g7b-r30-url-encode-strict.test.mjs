/* G7-B R30 URL query contract. Offline source test; no Host50, network, EXE, NSIS or CI. */
import test from "node:test";
import assert from "node:assert/strict";
import {execute,IDS} from "./ops.mjs";

const run=(route,input)=>execute(route,input).result;
test("G7-B R30: URL encode/decode rejects aliases and structured lossy data",()=>{
  assert.equal(IDS.length,50);
  assert.equal(new Set(IDS).size,50);
  const encoded=run("dev.url.query_encode",'{"x":"hello world","flag":true,"empty":null}');
  assert.equal(encoded,"x=hello+world&flag=true&empty=");
  assert.deepEqual(run("dev.url.query_decode",encoded),{x:"hello world",flag:"true",empty:""});
  assert.throws(()=>run("dev.url.query_encode",'{"X":"one","x":"two"}'),/DUPLICATE_QUERY_KEY/);
  assert.throws(()=>run("dev.url.query_encode",JSON.stringify({"é":1,"e\u0301":2})),/DUPLICATE_QUERY_KEY/);
  assert.throws(()=>run("dev.url.query_encode",'{"nested":{"a":1}}'),/QUERY_SCALAR_REQUIRED/);
  assert.throws(()=>run("dev.url.query_encode",'{"nested":[1,2]}'),/QUERY_SCALAR_REQUIRED/);
  assert.equal(run("dev.url.query_encode",'{"__proto__":"preserved"}'),"__proto__=preserved");
  const safe=run("dev.url.query_decode","__proto__=preserved");
  assert.equal(Object.hasOwn(safe,"__proto__"),true);
  assert.equal(safe.__proto__,"preserved");
  // Existing 50 routes, JSON empty nodes, CSV, and decode duplicate policy remain unchanged.
  assert.deepEqual(JSON.parse(JSON.stringify(run("data.json.flatten",'{"nested":{}}'))),{"nested":{}});
  assert.throws(()=>run("dev.url.query_decode","key=1&KEY=2"),/DUPLICATE_QUERY_KEY/);
});
