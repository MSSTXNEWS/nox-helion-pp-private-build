import assert from "node:assert/strict";
import { execute, IDS } from "./ops.mjs";
const serialize = rows => execute("data.csv.stringify", JSON.stringify(rows)).result;
assert.throws(() => serialize([{id:"1",payload:{secret:"SENSITIVE"}}]), /CSV_NONSCALAR_CELL/);
assert.throws(() => serialize([{id:"1",payload:["a","b"]}]), /CSV_NONSCALAR_CELL/);
assert.throws(() => serialize([{},{}]), /CSV_SCHEMA_MISMATCH/);
const result = serialize([{id:"1",name:'A,"B"',ok:true},{name:"C",id:"2",ok:false}]);
assert.deepEqual(execute("data.csv.parse", result).result, [{id:"1",name:'A,"B"',ok:"true"},{id:"2",name:"C",ok:"false"}]);
assert.equal(IDS.length, 50);
