import test from "node:test";
import assert from "node:assert/strict";
import { execute, IDS } from "./ops.mjs";

const run = (route, input, options = {}) => execute(route, input, options).result;

test("G7-B R30: lossless CSV, unambiguous HTTP URL/query inputs, 50 original routes", () => {
  assert.equal(IDS.length, 50);
  assert.equal(new Set(IDS).size, 50);

  assert.deepEqual(run("data.csv.parse", 'name,note\nAda,"a\r\nb"'), [{name:"Ada",note:"a\r\nb"}]);
  assert.deepEqual(run("data.csv.parse", "a,b\r1,2\r"), [{a:"1",b:"2"}]);
  assert.deepEqual(run("data.csv.parse", 'value\n""\n\n""'), [{value:""},{value:""}]);
  assert.throws(() => run("data.csv.parse", "Owner,owner\nA,B"), /INVALID_CSV_HEADER/);
  assert.throws(() => run("data.csv.parse", "naïve,nai\u0308ve\nA,B"), /INVALID_CSV_HEADER/);
  assert.throws(() => run("data.csv.parse", 'a\n"ok"junk'), /INVALID_CSV_TRAILING_CHAR/);
  assert.throws(() => run("data.csv.parse", 'a\nx"y'), /INVALID_CSV_QUOTE/);

  const exported = run("data.csv.stringify", JSON.stringify([{name:"Ada"}, {name:"Bob",score:9}]));
  assert.equal(exported, "name,score\nAda,\nBob,9");
  const nested = run("data.csv.stringify", JSON.stringify([{payload:{a:1},list:[2,3]}]));
  assert.deepEqual(run("data.csv.parse", nested), [{payload:'{"a":1}',list:"[2,3]"}]);
  assert.throws(() => run("data.csv.stringify", '[{"name":"Ada"},null]'), /CSV_RECORD_OBJECT_REQUIRED/);
  assert.throws(() => run("data.csv.stringify", '[{"Name":1,"name":2}]'), /INVALID_CSV_HEADER/);

  const url = run("dev.url.inspect", "https://example.org/p?q=1");
  assert.equal(url.host, "example.org");
  assert.throws(() => run("dev.url.inspect", "https://user:pass@example.org/"), /URL_CREDENTIALS_FORBIDDEN/);
  assert.throws(() => run("dev.url.inspect", "https://example.org\\@evil.org"), /URL_AMBIGUOUS_INPUT/);
  assert.throws(() => run("dev.url.inspect", "https://example.org\n.evil.org/"), /URL_AMBIGUOUS_INPUT/);
  assert.throws(() => run("dev.url.inspect", "file:///tmp/x"), /HTTP_ONLY/);

  assert.deepEqual(run("dev.url.query_decode", "x=1&name=Ada"), {x:"1",name:"Ada"});
  for (const query of ["x=1&x=2", "Owner=1&owner=2", "na%C3%AFve=1&nai%CC%88ve=2"]) {
    assert.throws(() => run("dev.url.query_decode", query), /DUPLICATE_QUERY_KEY/);
  }
  const proto = run("dev.url.query_decode", "__proto__=data");
  assert.equal(Object.getPrototypeOf(proto), Object.prototype);
  assert.equal(Object.getOwnPropertyDescriptor(proto,"__proto__").value,"data");
});
