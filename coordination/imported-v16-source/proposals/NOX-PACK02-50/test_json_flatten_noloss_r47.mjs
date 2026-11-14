import assert from "node:assert/strict";
import { execute, IDS } from "./ops.mjs";
const flatten = text => execute("data.json.flatten", text).result;
for (const sample of [
  '{"a.b":1,"a":{"b":2}}',
  '{"a":{"b":2},"a.b":1}'
]) {
  assert.throws(() => flatten(sample), /JSON_FLATTEN_PATH_COLLISION/,
    "ambiguous dotted JSON paths must fail closed without silently losing a value");
}
const withProto = flatten('{"__proto__":null,"safe":1}');
assert.equal(Object.hasOwn(withProto, "__proto__"), true);
assert.equal(withProto["__proto__"], null);
assert.deepEqual(JSON.parse(JSON.stringify(withProto)), JSON.parse('{"__proto__":null,"safe":1}'));
assert.deepEqual(JSON.parse(JSON.stringify(flatten('{"a":{"b":2},"c":3}'))), {"a.b":2,c:3});
assert.equal(IDS.length, 50);
console.log("PACK02 JSON flatten no-loss/prototype: PASS");
