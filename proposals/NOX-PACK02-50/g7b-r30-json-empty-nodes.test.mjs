/* G7-B R30 source-only JSON regression. No EXE/NSIS/CI/Host50 execution. */
import test from "node:test";
import assert from "node:assert/strict";
import {execute, IDS} from "./ops.mjs";
const run=(route,input,options={})=>execute(route,input,options).result;

test("G7-B R30: preserve empty JSON containers and existing collision/no-loss contracts",()=>{
  assert.equal(IDS.length,50);
  assert.equal(new Set(IDS).size,50);
  const data=run("data.json.flatten",'{"emptyObject":{},"emptyArray":[],"nested":{"object":{},"array":[]},"list":[{},[],1]}');
  assert.deepEqual(JSON.parse(JSON.stringify(data)),{
    emptyObject:{},emptyArray:[],
    "nested.object":{},"nested.array":[],
    "list.0":{},"list.1":[],"list.2":1
  });
  assert.deepEqual(JSON.parse(JSON.stringify(run("data.json.flatten",'{"a":{"b":2},"flag":false}'))),
    {"a.b":2,flag:false});
  assert.deepEqual(JSON.parse(JSON.stringify(run("data.json.flatten","{}"))),{});
  assert.deepEqual(JSON.parse(JSON.stringify(run("data.json.flatten","[]"))),{});
  assert.throws(()=>run("data.json.flatten",'{"a.b":1,"a":{"b":2}}'),/JSON_PATH_COLLISION/);
  const safe=run("data.json.flatten",'{"__proto__":null,"ok":1}');
  assert.equal(Object.getPrototypeOf(safe),null);
  assert.equal(Object.hasOwn(safe,"__proto__"),true);
  assert.equal(safe.__proto__,null);
  assert.deepEqual(run("dev.json.compare",'{"settings":{}}',{
    compare:'{"settings":{"enabled":true}}'
  }),[
    {path:"settings",before:{},after:null},
    {path:"settings.enabled",before:null,after:true}
  ]);
});
