import test from "node:test";
import assert from "node:assert/strict";
import {execute, IDS} from "./ops.mjs";

test("G7-B R09 CSV filter/sort require declared own columns without breaking real headers", () => {
  const data = "name,amount\nBob,2\nAlice,12\nBob,10";
  assert.deepEqual(
    execute("data.csv.filter", data, {field:"name",term:"Bob"}).result.map(r => r.amount),
    ["2","10"]
  );
  assert.deepEqual(
    execute("data.csv.sort", data, {field:"amount"}).result.map(r => r.amount),
    ["2","10","12"]
  );
  for (const route of ["data.csv.filter", "data.csv.sort"]) {
    for (const field of ["amout", "Amount", "__proto__", "constructor", "toString", null, 0]) {
      assert.throws(() => execute(route, data, {field,term:"Bob"}), /CSV_UNKNOWN_FIELD/,
        route+" field "+String(field));
    }
    assert.deepEqual(execute(route, "", {field:"unused",term:""}).result, []);
  }
  const realReserved = "constructor,amount\nA,2\nB,1";
  assert.deepEqual(
    execute("data.csv.filter", realReserved, {field:"constructor",term:"A"}).result,
    [{constructor:"A",amount:"2"}]
  );
  assert.deepEqual(
    execute("data.csv.sort", realReserved, {field:"constructor"}).result.map(r => r.constructor),
    ["A","B"]
  );
  assert.equal(IDS.length, 50, "retain every existing PACK02 action ID");
});
