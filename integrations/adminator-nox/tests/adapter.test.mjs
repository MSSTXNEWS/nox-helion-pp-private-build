import test from "node:test";
import assert from "node:assert/strict";
import {
  NOX_NATIVE_ROUTES,
  buildSparkline,
  formatMetric,
  validateRouteBindings
} from "../nox-adminator-adapter.mjs";

test("only canonical NOX route ids are accepted", () => {
  assert.deepEqual(validateRouteBindings({ chat: "commands", models: "model-library" }), {
    chat: "commands",
    models: "model-library"
  });
  assert.throws(() => validateRouteBindings({ admin: "delete-account" }),
    /NOX_ROUTE_BINDING_NOT_IN_CANONICAL_ALLOWLIST/);
  assert.equal(NOX_NATIVE_ROUTES.includes("model-library"), true);
});

test("missing metrics never become fabricated zeroes", () => {
  assert.equal(formatMetric(undefined), "—");
  assert.equal(formatMetric(NaN), "—");
  assert.equal(formatMetric(-1), "—");
  assert.equal(formatMetric(34.26), "34.3%");
});

test("sparklines require a real bounded numeric sample", () => {
  assert.equal(buildSparkline([1]), null);
  assert.equal(buildSparkline([1, NaN]), null);
  assert.equal(buildSparkline([1, 2, 3]).split(" ").length, 3);
});
