import assert from "node:assert/strict";
import { execute, IDS } from "./ops.mjs";
const stringify = rows => execute("data.csv.stringify", JSON.stringify(rows)).result;
const parse = text => execute("data.csv.parse", text).result;
for (const note of ["first\r\nsecond", "first\rsecond", "first\nsecond"]) {
  const rows = [{note}];
  assert.deepEqual(parse(stringify(rows)), rows, "quoted newline must round-trip byte-identically");
}
assert.deepEqual(parse("name,age\r\nAda,1\rBob,2\n"), [{name:"Ada",age:"1"},{name:"Bob",age:"2"}]);
assert.equal(IDS.length, 50);
console.log("PACK02 quoted CRLF/lone CR no-loss: PASS");
