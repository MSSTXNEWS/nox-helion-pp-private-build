import assert from "node:assert/strict";
import { execute, IDS } from "./ops.mjs";

const flatten = input => execute("data.json.flatten", input).result;
for (const input of [
  "{}",
  "[]",
  "{\"empty\":{},\"b\":1}",
  "{\"empty\":[],\"b\":1}",
  "{\"nested\":{\"list\":[{}]},\"b\":2}",
  "{\"nested\":{\"list\":[]},\"b\":2}"
]) {
  assert.throws(() => flatten(input), /JSON_FLATTEN_EMPTY_CONTAINER/,
    "empty JSON objects/arrays must fail closed rather than disappear");
}
for (const input of ['{"a.b":1,"a":{"b":2}}', '{"a":{"b":2},"a.b":1}']) {
  assert.throws(() => flatten(input), /JSON_FLATTEN_PATH_COLLISION/);
}
assert.deepEqual(JSON.parse(JSON.stringify(flatten('{"items":[1,2],"meta":{"ok":true}}'))),
  {"items.0":1,"items.1":2,"meta.ok":true});
const proto = flatten('{"__proto__":null,"safe":1}');
assert.equal(Object.hasOwn(proto, "__proto__"), true);
assert.equal(proto.__proto__, null);
assert.equal(IDS.length, 50);
console.log("PACK02 JSON flatten empty-container no-loss: PASS");
