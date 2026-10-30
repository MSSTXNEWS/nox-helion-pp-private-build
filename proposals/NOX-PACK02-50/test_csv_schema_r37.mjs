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

test("filter and sort reject unknown and inherited CSV fields",()=>{
 for(const routeId of ["data.csv.filter","data.csv.sort"])
  for(const field of ["missing","toString","__proto__"])
   assert.throws(()=>execute(routeId,"name,count\nAlice,2",{field,term:"Alice"}),/UNKNOWN_CSV_FIELD/);
});
test("filter/sort use header-only CSV schema",()=>{
 for(const routeId of ["data.csv.filter","data.csv.sort"]){
  assert.deepEqual(execute(routeId,"name,count\n",{field:"name"}).result,[]);
  assert.throws(()=>execute(routeId,"name,count\n",{field:"absent"}),/UNKNOWN_CSV_FIELD/);
 }
});
test("valid CSV filter and numeric sort remain unchanged",()=>{
 const input="name,count\nAlice,2\nBob,10";
 assert.deepEqual(execute("data.csv.filter",input,{field:"name",term:"ali"}).result,[{name:"Alice",count:"2"}]);
 assert.deepEqual(execute("data.csv.sort",input,{field:"count"}).result,[{name:"Alice",count:"2"},{name:"Bob",count:"10"}]);
});
