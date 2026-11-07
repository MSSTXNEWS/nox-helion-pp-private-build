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
function makeButton(id) {
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
    focus() { this.focused = true; }
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
  const buttons = ids.map(makeButton), panels = ids.map(makePanel);
  const side = {scrollTop:160}, title = {textContent:""}, requests = [];
  const document = {
    querySelectorAll(selector) {
      if (selector === ".core[data-route]" || selector === "button.core[data-route]")
        return buttons;
      if (selector === ".panel[data-panel]") return panels;
      throw new Error("F03_UNEXPECTED_SELECTOR_" + selector);
    },
    querySelector(selector) {
      assert.equal(selector, "aside.side");
      return side;
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
  requests.length=0;
  const titleBefore=title.textContent;
  assert.equal(context.route("__proto__"),false,"F03_UNTRUSTED_ROUTE_ACCEPTED");
  assert.deepEqual(requests, [],"F03_UNTRUSTED_ROUTE_SENT_IPC");
  assert.equal(title.textContent,titleBefore);
  function press(index, key) {
    const event={key, prevented:false,preventDefault(){this.prevented=true;}};
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
}
run(false); // desktop scroll remains functional after long history or notes
run(true);  // compact 320/390/800 scroll and all eight routes
assert.match(html, /@media\(max-width:1000px\)\{body\{overflow:auto\}/);
assert.match(html, /@media\(max-width:1000px\) and \(max-height:620px\)/);
assert.match(html, /\.side\{height:auto;overflow-x:hidden;overflow-y:auto\}/);
console.log("F03 R8 SOURCE_ONLY PASS: 8 routes × 2 layouts, native IPC mapping, notes refresh, keyboard, ARIA, scroll");