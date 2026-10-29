/* G7-B R30: URL inspector must not silently accept lossy percent/UTF-8 or malformed UTF-16.
   Offline Node source-only test; no network requests, Host50, EXE, NSIS or CI. */
import test from "node:test";
import assert from "node:assert/strict";
import {execute, IDS} from "./ops.mjs";

const inspect = url => execute("dev.url.inspect", url).result;

test("G7-B R30: inspector checks raw URL encoding before WHATWG normalization", () => {
  assert.equal(IDS.length, 50);
  assert.equal(new Set(IDS).size, 50);
  for (const bad of [
    "https://example.org/?q=%FF",
    "https://example.org/%",
    "https://example.org/%2G",
    "https://example.org/?q=%C3%28",
    "https://example.org/?q=%ED%A0%80",
    "https://example.org/#%FF",
    "https://example.org/\uD800",
  ]) {
    assert.throws(() => inspect(bad), /INVALID_URL_ENCODING/, bad);
  }
  assert.deepEqual(inspect("https://example.org/a%2Fb?x=%E2%9C%85#ok"), {
    scheme: "https:",
    host: "example.org",
    path: "/a%2Fb",
    query: [["x", "✅"]],
    fragment: "#ok",
  });
  assert.deepEqual(inspect("https://example.org/?q=%25").query, [["q", "%"]]);
  assert.throws(() => inspect("https://user:pw@example.org/"), /URL_CREDENTIALS_FORBIDDEN/);
  assert.throws(() => inspect("https://example.org/\\path"), /URL_AMBIGUOUS_INPUT/);
});
