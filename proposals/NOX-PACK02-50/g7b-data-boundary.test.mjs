import test from "node:test";
import assert from "node:assert/strict";
import {execute, IDS} from "./ops.mjs";

test("G7-B: PACK02 CSV/JSON/URL input boundaries preserve 50 routes", () => {
  assert.equal(IDS.length, 50);
  assert.throws(
    () => execute("data.csv.parse", 'id,name\n1,"Alice"evil'),
    /INVALID_CSV_TRAILING_CHAR/
  );
  assert.throws(
    () => execute("data.csv.parse", 'id,name\n1,Al"ice"'),
    /INVALID_CSV_QUOTE/
  );
  assert.deepEqual(
    execute("data.csv.parse", 'id,note\n1,"hi, ""friend""\nnext"').result,
    [{id:"1", note:'hi, "friend"\nnext'}]
  );
  const flattened = execute("data.json.flatten", '{"__proto__":null,"ok":1}').result;
  assert.equal(Object.prototype.hasOwnProperty.call(flattened,"__proto__"), true);
  assert.equal(flattened.__proto__, null);
  assert.equal(flattened.ok, 1);
  assert.throws(
    () => execute("data.json.flatten", '{"a.b":1,"a":{"b":2}}'),
    /JSON_PATH_COLLISION/
  );
  assert.throws(
    () => execute("dev.url.inspect", "https://user:secret@example.org/path"),
    /URL_CREDENTIALS_FORBIDDEN/
  );
  assert.equal(
    execute("dev.url.inspect", "https://example.org/path?q=1").result.host,
    "example.org"
  );
});
