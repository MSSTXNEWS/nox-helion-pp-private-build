import test from "node:test";
import assert from "node:assert/strict";
import {
  NOX_NATIVE_ROUTES,
  buildSparkline,
  classifyNativeResponse,
  formatMetric,
  validateRouteBindings
} from "../nox-adminator-adapter.mjs";

test("only canonical NOX route ids are accepted", () => {
  assert.deepEqual(
    { ...validateRouteBindings({ chat: "helion.chat", models: "models.catalog" }) },
    { chat: "helion.chat", models: "models.catalog" }
  );
  assert.throws(() => validateRouteBindings({ admin: "delete-account" }),
    /NOX_ROUTE_BINDING_NOT_IN_CANONICAL_ALLOWLIST/);
  assert.throws(() => validateRouteBindings({ models: "model-library" }),
    /NOX_ROUTE_BINDING_NOT_IN_CANONICAL_ALLOWLIST/);
  assert.equal(NOX_NATIVE_ROUTES.includes("models.catalog"), true);
  assert.equal(NOX_NATIVE_ROUTES.includes("chat.commands"), true);
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

test("native result classification requires exact route correlation and real host terminal state", () => {
  assert.deepEqual(classifyNativeResponse("models.catalog", {
    routeId: "models.catalog", state: "COMPLETED", requestId: "native-1"
  }), { state: "confirmed", requestId: "native-1" });
  assert.deepEqual(classifyNativeResponse("models.pull", {
    routeId: "models.pull", state: "QUEUED", requestId: "native-2"
  }), { state: "queued", requestId: "native-2" });
  assert.deepEqual(classifyNativeResponse("chat.stop", {
    routeId: "chat.stop", state: "STOP_REQUESTED", requestId: "native-3"
  }), { state: "stop_requested", requestId: "native-3" });
  assert.equal(classifyNativeResponse("chat.commands", {
    routeId: "models.catalog", state: "COMPLETED"
  }).state, "hold");
  assert.equal(classifyNativeResponse("models.pull", {
    routeId: "models.pull", state: "HOLD", errorCode: "CAPABILITY_HOLD"
  }).state, "hold");
});
