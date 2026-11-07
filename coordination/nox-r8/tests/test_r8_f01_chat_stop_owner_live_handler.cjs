"use strict";
/* F01 independent SOURCE_ONLY runner: execute the ORIGINAL embedded WebView2
   SEND/STOP/native-receipt handlers in V8. This is not a simulated Qwen reply,
   an owner-PC test, a SQLite durability proof, or release acceptance.
   Real Windows WPF/SQLite WAL and owner Qwen have separate evidence gates. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const sourceCandidates = [
  path.resolve(__dirname, "src", "index.html"),
  path.resolve(__dirname, "..", "overrides", "src", "index.html")
];
const sourcePath = sourceCandidates.find(x => fs.existsSync(x));
assert.ok(sourcePath, "F01_WEBVIEW2_ORIGINAL_SOURCE_MISSING_HOLD");
const html = fs.readFileSync(sourcePath, "utf8");
const sendStart = html.indexOf("$('send').onclick=()=>");
const stopEnd = html.indexOf(";$('prompt').onkeydown=", sendStart);
const receiptStart = html.indexOf("window.chrome?.webview?.addEventListener('message',e=>{");
const receiptEnd = html.indexOf("\n}});", receiptStart);
assert.ok(sendStart >= 0 && stopEnd > sendStart && receiptStart >= 0 && receiptEnd > receiptStart,
  "F01_NATIVE_OWNER_HANDLER_MISSING_HOLD");
const originalHandlers = html.slice(sendStart, stopEnd + 1) + "\n" +
  html.slice(receiptStart, receiptEnd + 5);

function fixture({chatAccepted = true, stopAccepted = true, confirmRepeat = false} = {}) {
  const nodes = {
    send: {}, stop: {}, prompt: {value: ""},
    streamHint: {textContent: "Ответ завершён и сохранён в SQLite."},
    messages: {},
    generation: {classList: {remove(){}, add(){}}}
  };
  const outbound = [], routes = [], bridge = {chatAccepted, stopAccepted};
  let next = 0, receiver = null, confirmations = 0;
  const state = {
    busy: false, activeChatId: null, pendingStopId: null,
    pendingChatDraft: null, visibleDraftPersona: "KV",
    lastAnswer: "", responseBox: null, uncertainChatKeys: new Set(),
    uncertainChatKey: (persona, text) => persona + ":" + text,
    personaDrafts: new Map(),
    nextChatId: () => "f01_real_handler_" + (++next),
    post: (type, payload) => {
      outbound.push({type, payload});
      return type === "chat" ? bridge.chatAccepted : type === "stop" ? bridge.stopAccepted : true;
    },
    entry: () => ({lastChild: {textContent: ""}}),
    $: id => {
      assert.ok(Object.prototype.hasOwnProperty.call(nodes, id), "F01_UNEXPECTED_DOM:" + id);
      return nodes[id];
    },
    route: id => { routes.push(id); return true; },
    window: {
      confirm: () => { confirmations++; return confirmRepeat; },
      noxVisual: {setEnergy(){}},
      chrome: {webview: {addEventListener(name, handler) {
        assert.equal(name, "message");
        receiver = handler;
      }}}
    }
  };
  vm.runInNewContext(originalHandlers, state, {timeout: 2000, filename: "original-nox-r8-index.html"});
  assert.equal(typeof receiver, "function", "F01_NATIVE_RECEIVER_NOT_BOUND_HOLD");
  return {
    nodes, outbound, routes, bridge, state,
    deliver(type, value) { receiver({data: {type, value}}); },
    confirmations() { return confirmations; }
  };
}

const denied = fixture({chatAccepted: false});
denied.nodes.prompt.value = "Не потерять черновик";
denied.nodes.send.onclick();
assert.equal(denied.state.busy, false, "F01_DENIED_CHAT_MUST_NOT_LOCK_HOLD");
assert.equal(denied.state.activeChatId, null, "F01_DENIED_CHAT_OWNER_HOLD");
assert.equal(denied.nodes.prompt.value, "Не потерять черновик", "F01_DENIED_CHAT_DRAFT_LOST_HOLD");
assert.equal(denied.outbound.filter(x => x.type === "chat").length, 1);
assert.match(denied.nodes.streamHint.textContent, /Черновик сохранён/);

const run = fixture();
run.nodes.prompt.value = "Qwen, проверь STOP";
run.nodes.send.onclick();
const owner = run.state.activeChatId;
assert.ok(owner && run.state.busy && run.state.pendingStopId === null);
assert.equal(run.nodes.streamHint.textContent, "Генерация ответа · не сохранено",
  "F01_PREVIOUS_SQLITE_SUCCESS_BANNER_LEAK_HOLD");
run.nodes.stop.onclick();
run.nodes.stop.onclick();
assert.equal(run.outbound.filter(x => x.type === "stop").length, 1,
  "F01_DUPLICATE_STOP_NATIVE_POST_HOLD");
assert.equal(run.outbound.find(x => x.type === "stop").payload.requestId, owner,
  "F01_STOP_WRONG_REQUEST_LEASE_HOLD");
// F01 STOP in-flight race: an already-queued token from the SAME request may
// arrive after native STOP dispatch and before its matching complete receipt.
// It must not remain visible as a purported saved answer.
run.deliver("token", {requestId: owner, text: "TOKEN_AFTER_STOP_DISPATCH"});
assert.equal(run.state.lastAnswer, "", "F01_INFLIGHT_STOP_TOKEN_VISIBLE_HOLD");
assert.equal(run.state.responseBox.lastChild.textContent, "", "F01_INFLIGHT_STOP_DOM_VISIBLE_HOLD");
run.deliver("token", {requestId: "foreign_owner", text: "LATE"});
run.deliver("complete", {requestId: "foreign_owner", ok: true});
assert.ok(run.state.busy && run.state.activeChatId === owner,
  "F01_FOREIGN_RECEIPT_RELEASED_ACTIVE_OWNER_HOLD");
assert.equal(run.state.lastAnswer, "", "F01_FOREIGN_TOKEN_VISIBLE_HOLD");
run.deliver("complete", {requestId: owner, ok: false, stopped: true});
assert.equal(run.state.busy, false, "F01_STOP_RECEIPT_DID_NOT_UNLOCK_HOLD");
assert.equal(run.state.pendingStopId, null, "F01_STOP_DEDUP_LEASE_STUCK_HOLD");
assert.equal(run.nodes.prompt.value, "Qwen, проверь STOP", "F01_STOP_LOST_USER_DRAFT_HOLD");
assert.match(run.nodes.streamHint.textContent, /Частичный ответ не сохранён/,
  "F01_STOP_PARTIAL_MISREPORTED_SAVED_HOLD");

run.nodes.send.onclick();
const resumedOwner = run.state.activeChatId;
assert.notEqual(resumedOwner, owner, "F01_REUSE_STOPPED_REQUEST_ID_HOLD");
assert.equal(run.state.pendingStopId, null, "F01_NEW_CHAT_STOP_LEASE_STALE_HOLD");
assert.equal(run.nodes.streamHint.textContent, "Генерация ответа · не сохранено");
run.deliver("token", {requestId: resumedOwner, text: "Токен"});
assert.equal(run.state.lastAnswer, "Токен", "F01_ACTIVE_TOKEN_LOST_HOLD");
run.deliver("complete", {requestId: resumedOwner, ok: true});
assert.equal(run.state.busy, false, "F01_SUCCESS_RECEIPT_DID_NOT_UNLOCK_HOLD");
assert.equal(run.nodes.streamHint.textContent, "Ответ завершён и сохранён в SQLite.",
  "F01_SUCCESS_RECEIPT_MISSING_HOLD");
run.deliver("token", {requestId: resumedOwner, text: "ПОЗДНО"});
assert.equal(run.state.lastAnswer, "Токен", "F01_POST_COMPLETE_LATE_TOKEN_HOLD");

const failedStop = fixture({stopAccepted: false});
failedStop.nodes.prompt.value = "STOP при недоступном IPC";
failedStop.nodes.send.onclick();
failedStop.nodes.stop.onclick();
assert.equal(failedStop.state.pendingStopId, null, "F01_FAILED_STOP_BRIDGE_STUCK_HOLD");
failedStop.bridge.stopAccepted = true;
failedStop.nodes.stop.onclick();
assert.equal(failedStop.outbound.filter(x => x.type === "stop").length, 2,
  "F01_STOP_RETRY_AFTER_BRIDGE_FAILURE_HOLD");
assert.equal(failedStop.state.pendingStopId, failedStop.state.activeChatId);

const unknown = fixture({confirmRepeat: false});
unknown.nodes.prompt.value = "SQLite результат может быть неопределённым";
unknown.nodes.send.onclick();
unknown.deliver("complete", {
  requestId: unknown.state.activeChatId, ok: false, sqliteUnknown: true
});
assert.equal(unknown.state.busy, false);
assert.equal(unknown.nodes.prompt.value, "SQLite результат может быть неопределённым");
assert.match(unknown.nodes.streamHint.textContent, /Проверьте историю/);
const before = unknown.outbound.filter(x => x.type === "chat").length;
unknown.nodes.send.onclick();
assert.equal(unknown.outbound.filter(x => x.type === "chat").length, before,
  "F01_UNKNOWN_SQLITE_DUPLICATE_CHAT_DISPATCH_HOLD");
assert.equal(unknown.confirmations(), 1);
assert.ok(unknown.routes.includes("reflection"), "F01_UNKNOWN_SQLITE_HISTORY_ROUTE_HOLD");

console.log("F01 ORIGINAL_WEBVIEW2_SEND_STOP_RUNTIME_SOURCE_ONLY_PASS; OWNER_PC_QWEN_SQLITE_NOT_TESTED");
