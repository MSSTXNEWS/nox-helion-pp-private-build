"use strict";
/* F03 R8: executes original WebView2 route + keyboard handlers inside a mocked DOM.
   SOURCE_ONLY, not Windows WebView2 UIA, local Qwen or EXE acceptance. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
function source(name) {
  const candidates = [path.join(__dirname, "src", name),
    path.join(__dirname, "..", "overrides", "src", name)];
  const file = candidates.find(fs.existsSync);
  assert.ok(file, "F03_R8_ORIGINAL_SOURCE_MISSING_" + name);
  return fs.readFileSync(file, "utf8");
}
const html = source("index.html"), native = source("MainWindow.xaml.cs");
assert.match(native, /case "notes\.list": Send\("notes", ReadNotes\(\)\);/,
  "F03_NOTES_REFRESH_NATIVE_OWNER_ROUTE_MISSING");
const ids = [...html.matchAll(/<button class="core [^"]*" data-route="([^"]+)"/g)]
  .map(match => match[1]);
assert.deepEqual(ids, ["consciousness","atlas","reflection","nexus",
  "forge","core","voice","persona"], "F03_EIGHT_ORIGINAL_COREID_ROUTES_HOLD");
for (const id of ids) {
  assert.ok(html.includes('data-panel="' + id + '"'),
    "F03_ORIGINAL_PANEL_MISSING_" + id);
}
const lines = html.split(/\r?\n/);
const routeSource = lines.find(line => line.startsWith("function route(id)"));
const keyboardSource = lines.find(line => line.startsWith("const coreRouteButtons="));
assert.ok(routeSource && keyboardSource, "F03_ORIGINAL_ROUTE_HANDLER_MISSING");
const expected = {
  consciousness: ["health"],
  atlas: ["tasks.list"],
  reflection: ["history","notes.list","knowledge.stats"],
  nexus: ["health"],
  forge: ["training","learn.queue"],
  core: [],
  voice: [],
  persona: ["settings.get"]
};
function makeButton(id,onFocus=()=>{}) {
  const classes = new Set(), attrs = {}, handlers = {};
  return {
    dataset: {route:id}, attrs, handlers, focused:false,
    classList: {
      toggle(name, on) { if (on) classes.add(name); else classes.delete(name); },
      contains(name) { return classes.has(name); }
    },
    setAttribute(name, value) { attrs[name] = value; },
    removeAttribute(name) { delete attrs[name]; },
    addEventListener(type, handler) { handlers[type] = handler; },
    focus() { this.focused = true; onFocus(this); },
    closest() { return null; }
  };
}
function makePanel(id) {
  const classes = new Set();
  return {dataset:{panel:id},classList:{
    toggle(name, on) {if (on) classes.add(name);else classes.delete(name);},
    contains(name) {return classes.has(name);}
  }};
}
function run(compact) {
  let activeElement=null;
  const buttons = ids.map(id=>makeButton(id,element=>{activeElement=element;})), panels = ids.map(makePanel);
  const side = {scrollTop:160}, title = {textContent:""}, requests = [];
  const document = {
    get activeElement(){return activeElement;},
    querySelectorAll(selector) {
      if (selector === ".core[data-route]" || selector === "button.core[data-route]")
        return buttons;
      if (selector === ".panel[data-panel]") return panels;
      throw new Error("F03_UNEXPECTED_SELECTOR_" + selector);
    },
    querySelector(selector) {
      if(selector==="aside.side")return side;
      const match=selector.match(/^button\.core\[data-route="([^"]+)"\]$/);
      if(match)return buttons.find(button=>button.dataset.route===match[1])||null;
      throw new Error("F03_UNEXPECTED_QUERY_"+selector);
    }
  };
  const context = { document, window:{matchMedia:() => ({matches:compact})},
    headings:{consciousness:"CONSCIOUSNESS",atlas:"ATLAS / TASKS",
      reflection:"REFLECTION / HISTORY",nexus:"NEXUS / MODELS",
      forge:"FORGE / TRAINING",core:"CORE / LIVE CHAT",
      voice:"VOICE",persona:"PERSONA"},
    $:id => {assert.equal(id, "routeTitle");return title;},
    post:type => {requests.push(type);return true;}
  };
  vm.createContext(context);
  vm.runInContext(routeSource+"\n"+keyboardSource, context, {timeout:1500});
  for (const id of ids) {
    requests.length=0;
    side.scrollTop=170;
    assert.equal(context.route(id), true, "F03_VALID_ROUTE_REJECTED_"+id);
    assert.deepEqual(requests, expected[id], "F03_NATIVE_REQUESTS_MISMATCH_"+id);
    assert.deepEqual(buttons.filter(b=>b.classList.contains("active"))
      .map(b=>b.dataset.route), [id], "F03_ACTIVE_COREID_MISMATCH_"+id);
    assert.deepEqual(panels.filter(p=>p.classList.contains("active"))
      .map(p=>p.dataset.panel), [id], "F03_VISIBLE_PANEL_MISMATCH_"+id);
    assert.deepEqual(buttons.filter(b=>b.attrs["aria-current"]==="page")
      .map(b=>b.dataset.route), [id], "F03_ARIA_ROUTE_MISMATCH_"+id);
    assert.equal(side.scrollTop, 0, "F03_ROUTE_SCROLL_RESET_HOLD_"+id);
  }
  // B06 focus recovery: a route that hides a focused panel must hand focus
  // to its real CoreID button, not leave keyboard focus inside a hidden panel.
  activeElement={closest(selector){
    assert.equal(selector, ".panel[data-panel]");
    return panels.find(panel=>panel.dataset.panel==="forge");
  }};
  buttons[2].focused=false;
  assert.equal(context.route("reflection"),true);
  assert.equal(activeElement,buttons[2],"F03_HIDDEN_PANEL_KEYBOARD_FOCUS_HOLD");
  const outside={closest(){return null;}};
  activeElement=outside;
  assert.equal(context.route("atlas"),true);
  assert.equal(activeElement,outside,"F03_OUTSIDE_PANEL_FOCUS_HIJACK_HOLD");
  const within={closest(){return panels.find(panel=>panel.dataset.panel==="atlas");}};
  activeElement=within;
  assert.equal(context.route("atlas"),true);
  assert.equal(activeElement,within,"F03_SAME_PANEL_FOCUS_HIJACK_HOLD");
  requests.length=0;
  const titleBefore=title.textContent;
  assert.equal(context.route("__proto__"),false,"F03_UNTRUSTED_ROUTE_ACCEPTED");
  assert.deepEqual(requests, [],"F03_UNTRUSTED_ROUTE_SENT_IPC");
  assert.equal(title.textContent,titleBefore);
  function press(index, key, extra={}) {
    const event={key, prevented:false,preventDefault(){this.prevented=true;},...extra};
    buttons[index].handlers.keydown(event);
    return event;
  }
  assert.equal(press(0,"End").prevented,true);
  assert.equal(buttons.at(-1).focused,true);
  assert.equal(buttons.at(-1).attrs["aria-current"],"page");
  assert.equal(press(7,"Home").prevented,true);
  assert.equal(buttons[0].focused,true);
  assert.equal(press(0,"ArrowLeft").prevented,true);
  assert.equal(buttons[7].attrs["aria-current"],"page");
  assert.equal(press(7,"ArrowRight").prevented,true);
  assert.equal(buttons[0].attrs["aria-current"],"page");
  const titleAfter=title.textContent;
  assert.equal(press(0,"Tab").prevented,false,"F03_KEYBOARD_TAB_INTERCEPT_HOLD");
  assert.equal(title.textContent,titleAfter);
  // Native keyboard traversal must respect IME, accessibility and OS chords.
  for(const guard of [{ctrlKey:true},{altKey:true},{metaKey:true},{shiftKey:true},
      {isComposing:true},{keyCode:229},{repeat:true},{defaultPrevented:true}]){
    const oldFocus=activeElement, oldTitle=title.textContent, oldCount=requests.length;
    assert.equal(press(0,"ArrowRight",guard).prevented,false,"F03_NATIVE_KEY_GUARD_INTERCEPT_HOLD");
    assert.equal(activeElement,oldFocus,"F03_NATIVE_KEY_GUARD_FOCUS_HOLD");
    assert.equal(title.textContent,oldTitle,"F03_NATIVE_KEY_GUARD_ROUTE_HOLD");
    assert.equal(requests.length,oldCount,"F03_NATIVE_KEY_GUARD_IPC_HOLD");
  }
}
run(false); // desktop scroll remains functional after long history or notes
run(true);  // compact 320/390/800 scroll and all eight routes
assert.match(html, /@media\(max-width:1000px\)\{body\{overflow:auto\}/);
assert.match(html, /@media\(max-width:1000px\) and \(max-height:620px\)/);
assert.match(html, /\.side\{height:auto;overflow-x:hidden;overflow-y:auto\}/);
assert.match(native, /checks\["f03_compact_native_coreid_focus_320_390_800"\] = "PASS";/,
  "F03_NATIVE_COMPACT_CHECKPOINT_MISSING");
assert.match(native, /const expectedRoutes = \['consciousness','atlas','reflection','nexus',/,
  "F03_NATIVE_COMPACT_EIGHT_ROUTE_WALK_MISSING");
assert.match(native, /const focusRecovered = document\.activeElement === reflection;/,
  "F03_NATIVE_COMPACT_HIDDEN_FOCUS_RECOVERY_MISSING");
assert.match(native, /f03_webview2_injected_gpu_context_fallback"\] = "PASS"/,
  "F03_REAL_WEBVIEW2_GPU_EVENT_RECEIPT_MISSING");
assert.match(native, /f03_webview2_emulated_reduced_motion"\] = "PASS"/,
  "F03_REAL_WEBVIEW2_EMULATED_REDUCED_MEDIA_RECEIPT_MISSING");
assert.match(native, /CallDevToolsProtocolMethodAsync\(/,
  "F03_EDGE_WEBVIEW2_REDUCED_MEDIA_NOT_EMULATED");
// F03 owner same-EXE QA must fail closed if a native accessibility/GPU/OS
// receipt was missing or came from a source-only mock.  The owner script is
// original; CI copied CJS lives at r8/, so resolve both honest source layouts.
const ownerQaCandidates = [
  path.join(__dirname, "..", "qa", "NOX_R8_OWNER_SAMESHA_E2E.ps1"),
  path.join(__dirname, "..", "coordination", "nox-r8", "qa", "NOX_R8_OWNER_SAMESHA_E2E.ps1")
];
const ownerQaPath=ownerQaCandidates.find(fs.existsSync);
assert.ok(ownerQaPath, "F03_OWNER_SAMESHA_QA_SCRIPT_MISSING");
const ownerQa=fs.readFileSync(ownerQaPath,"utf8");
const requiredOwnerUi=ownerQa.match(/\$mustPass=if\(\$Restart\)\s*\{[\s\S]*?\}\s*else\s*\{([\s\S]*?)\n\s*\}/);
assert.ok(requiredOwnerUi, "F03_OWNER_NATIVE_UI_MUSTPASS_BLOCK_MISSING");
for(const key of [
  "f03_compact_native_coreid_focus_320_390_800",
  "f03_webview2_chromium_input_keyboard",
  "f03_webview2_injected_gpu_context_fallback",
  "f03_webview2_emulated_reduced_motion"
]){
  assert.ok(requiredOwnerUi[1].includes("'"+key+"'"),"F03_OWNER_NATIVE_UI_RECEIPT_NOT_REQUIRED_"+key);
}
assert.match(ownerQa, /if\(\$value -cne 'PASS'\)\s*\{\s*throw "NATIVE_UI_CHECK_\$\(\$key\)_HOLD"\s*\}/,
  "F03_OWNER_NATIVE_UI_GATE_NOT_FAIL_CLOSED");
console.log("F03 R8 SOURCE_ONLY PASS: 8 routes × 2 layouts, native IPC mapping, notes refresh, keyboard, ARIA, scroll");