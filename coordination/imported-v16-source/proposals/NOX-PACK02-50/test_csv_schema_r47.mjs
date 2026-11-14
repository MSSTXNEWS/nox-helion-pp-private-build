import assert from "node:assert/strict";
import { execute, IDS } from "./ops.mjs";

const pack = rows => execute("data.csv.stringify", JSON.stringify(rows)).result;
assert.throws(() => pack([{id:"1",name:"A"},{id:"2",phone:"PRIVATE"}]), /CSV_SCHEMA_MISMATCH/);
assert.throws(() => pack([{id:"1",name:"A"},{id:"2"}]), /CSV_SCHEMA_MISMATCH/);
assert.throws(() => pack([{id:"1"},null]), /CSV_SCHEMA_MISMATCH/);
const value = pack([{id:"1",name:'A,"B"'},{name:"C",id:"2"}]);
assert.deepEqual(execute("data.csv.parse",value).result, [{id:"1",name:'A,"B"'},{id:"2",name:"C"}]);
assert.equal(IDS.length, 50);
