import test from "node:test";
import assert from "node:assert/strict";
import { execute, IDS } from "./ops.mjs";

// R30 G7-B regression: a missing key and an explicit JSON null must not be reported identically.
// Preserve the legacy before/after values; add presence evidence without changing 50 operation IDs.
const compare = (before, after) =>
  execute("dev.json.compare", JSON.stringify(before), { compare: JSON.stringify(after) }).result;

test("G7-B JSON compare disambiguates missing and null without losing existing routes", () => {
  assert.equal(IDS.length, 50);
  assert.equal(new Set(IDS).size, 50);

  assert.deepEqual(compare({}, { x: null }), [
    { path: "x", before: null, after: null, beforePresent: false, afterPresent: true },
  ]);
  assert.deepEqual(compare({ x: null }, {}), [
    { path: "x", before: null, after: null, beforePresent: true, afterPresent: false },
  ]);
  assert.deepEqual(compare({ x: null }, { x: null }), []);

  assert.deepEqual(compare({ x: 0 }, { x: null }), [
    { path: "x", before: 0, after: null, beforePresent: true, afterPresent: true },
  ]);
  assert.deepEqual(compare({ a: {} }, { a: { child: null } }), [
    { path: "a", before: {}, after: null, beforePresent: true, afterPresent: false },
    { path: "a.child", before: null, after: null, beforePresent: false, afterPresent: true },
  ]);

  assert.throws(
    () => execute("dev.json.compare", '{"a.b":1,"a":{"b":2}}', { compare: "{}" }),
    /JSON_PATH_COLLISION/,
  );
});
