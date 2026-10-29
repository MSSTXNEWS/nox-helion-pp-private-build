/* G7-B R30: malformed URL encoding, UTF-8 and surrogate-loss regression.
   Offline source test only: no Host50, Windows, network, EXE, NSIS or CI. */
import test from "node:test";
import assert from "node:assert/strict";
import {execute,IDS} from "./ops.mjs";

const run=(route,input)=>execute(route,input).result;
test("G7-B R30: query encode/decode preserve valid Unicode and reject malformed input",()=>{
  assert.equal(IDS.length,50);
  assert.equal(new Set(IDS).size,50);
  const expected="emoji=%F0%9F%98%8A&name=%D0%9F%D1%80%D0%B8%D0%B2%D0%B5%D1%82+%D0%BC%D0%B8%D1%80";
  assert.equal(run("dev.url.query_encode",'{"emoji":"😊","name":"Привет мир"}'),expected);
  assert.deepEqual(run("dev.url.query_decode",expected),{emoji:"😊",name:"Привет мир"});
  for(const bad of ["x=%","x=%2G","x=%FF","x=%E0%A4%A","x=%ED%A0%80","x=%C3%28","x=\uD800"]){
    assert.throws(()=>run("dev.url.query_decode",bad),/INVALID_QUERY_ENCODING/,bad);
  }
  for(const bad of ['{"bad":"\\ud800"}','{"\\ud800":"bad"}']){
    assert.throws(()=>run("dev.url.query_encode",bad),/INVALID_QUERY_ENCODING/,bad);
  }
  assert.throws(()=>run("dev.url.query_decode","x=1&X=2"),/DUPLICATE_QUERY_KEY/);
  assert.throws(()=>run("dev.url.query_encode",'{"é":1,"e\\u0301":2}'),/DUPLICATE_QUERY_KEY/);
  assert.throws(()=>run("dev.url.query_encode",'{"x":[1]}'),/QUERY_SCALAR_REQUIRED/);
  const safe=run("dev.url.query_decode","__proto__=safe");
  assert.equal(Object.hasOwn(safe,"__proto__"),true);
  assert.equal(safe.__proto__,"safe");
});
