import test from "node:test";
import assert from "node:assert/strict";
import {execute, IDS} from "./ops.mjs";

test("G7-B PACK02 CSV select rejects missing or inherited headers without fabricating data", () => {
  const source = "name,amount\nAlice,12\nBob,34";
  assert.deepEqual(
    execute("data.csv.select", source, {fields:"amount,name"}).result,
    [{amount:"12",name:"Alice"},{amount:"34",name:"Bob"}]
  );
  for (const field of ["amout","Amount","constructor","__proto__"]) {
    assert.throws(
      () => execute("data.csv.select", source, {fields:"name,"+field}),
      /CSV_UNKNOWN_FIELD/
    );
  }
  assert.deepEqual(
    execute("data.csv.select", 'name,note\nA,"hello, world"', {fields:"note"}).result,
    [{note:"hello, world"}]
  );
  assert.equal(IDS.length, 50, "existing 50 PACK02 route IDs must remain intact");
});
