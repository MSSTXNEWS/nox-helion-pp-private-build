import test from "node:test";
import assert from "node:assert/strict";
import {execute} from "./ops.mjs";

test("CSV header-only schema survives stats with zero data rows",()=>{
  assert.deepEqual(execute("data.csv.stats","name,count,note\n").result,{
    rows:0,columns:["name","count","note"],emptyCells:0
  });
});
test("CSV selection refuses unknown columns instead of silently dropping data",()=>{
  assert.throws(()=>execute("data.csv.select","name,note\nAlice,ok",{fields:"name,missing"}),/UNKNOWN_CSV_FIELD/);
});
test("CSV selection rejects duplicate fields and empty projection",()=>{
  assert.throws(()=>execute("data.csv.select","a,b\nx,y",{fields:"a,a"}),/UNKNOWN_CSV_FIELD/);
  assert.throws(()=>execute("data.csv.select","a,b\nx,y",{fields:""}),/UNKNOWN_CSV_FIELD/);
});
test("CSV valid selection preserves expected values",()=>{
  const out=execute("data.csv.select",'name,note\nAlice,"hi, there"',{fields:"note,name"});
  assert.deepEqual(out.result,[{note:"hi, there",name:"Alice"}]);
});
test("CSV malformed width remains a hard error",()=>{
  assert.throws(()=>execute("data.csv.parse","a,b\nonlyone"),/CSV_WIDTH_MISMATCH/);
});
