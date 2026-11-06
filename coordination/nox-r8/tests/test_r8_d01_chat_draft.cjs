"use strict";
/* D01 R8 SOURCE_ONLY. Executes the production click handler, not a simulated product UI.
   Native Windows integration is separately gated by the real WPF/WebView2 smoke. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, 'src', 'index.html'), 'utf8');
assert.match(html, /<textarea[^>]*id="prompt"[^>]*maxlength="32000"/);
const start = html.indexOf("$('send').onclick=()=>");
const end = html.indexOf("\n$('stop').onclick=", start);
assert.ok(start > 0 && end > start, 'D01 ORIGINAL_CHAT_HANDLER_MISSING');
const code = html.slice(start, end);
function scenario(draft, bridge, locked = false) {
  const nodes = {send: {}, prompt: {value: draft}, streamHint: {textContent: ''}, messages: {}};
  const sent = [], shown = [];
  const context = {
    $: id => {assert.ok(nodes[id], 'UNEXPECTED_DOM_NODE:' + id); return nodes[id];},
    post: (type, payload) => {sent.push({type, payload}); return bridge;},
    entry: (_container, value, label) => {shown.push({value, label}); return {lastChild: {textContent: ''}};},
    nextChatId: () => 'r8d01_owner_1234',
    busy: locked, activeChatId: null, responseBox: null, lastAnswer: 'old'
  };
  vm.runInNewContext(code, context, {timeout: 1500});
  nodes.send.onclick();
  return {nodes, sent, shown, context};
}
let a = scenario('Несохранённый черновик', false);
assert.equal(a.nodes.prompt.value, 'Несохранённый черновик');
assert.equal(a.shown.length, 0);
assert.equal(a.context.busy, false);
assert.equal(a.context.activeChatId, null);
assert.match(a.nodes.streamHint.textContent, /Черновик сохранён/);
a = scenario('я'.repeat(32001), true);
assert.equal(a.sent.length, 0);
assert.equal(a.nodes.prompt.value.length, 32001);
assert.equal(a.context.busy, false);
assert.equal(a.shown.length, 0);
a = scenario('   ', true);
assert.equal(a.sent.length, 0);
assert.equal(a.nodes.prompt.value, '   ');
a = scenario('Второй запрос', true, true);
assert.equal(a.sent.length, 0);
assert.equal(a.nodes.prompt.value, 'Второй запрос');
a = scenario('  Привет NOX  ', true);
assert.equal(a.sent.length, 1);
assert.equal(a.sent[0].type, 'chat');
assert.equal(a.sent[0].payload.text, 'Привет NOX');
assert.equal(a.sent[0].payload.requestId, 'r8d01_owner_1234');
assert.equal(a.shown.length, 2);
assert.equal(a.nodes.prompt.value, '');
assert.equal(a.context.busy, true);
assert.equal(a.context.activeChatId, 'r8d01_owner_1234');
console.log('D01 R8 SOURCE_ONLY PASS: offline draft, 32000 guard, empty, busy, native dispatch');

/* D01 compact/IME source regression: execute the production keyboard handler.
   Scrollable compact panel must keep native SEND/STOP/routes accessible. */
assert.match(html, /\.side\{height:auto;overflow-x:hidden;overflow-y:auto\}/,
  'D01_COMPACT_SIDE_SCROLL_HOLD');
assert.doesNotMatch(html, /\.side\{height:auto;overflow:hidden\}/);
const keyboardLine = html.split('\n').find(line => line.includes("$('prompt').onkeydown="));
assert.ok(keyboardLine, 'D01_CHAT_KEYBOARD_HANDLER_MISSING');
const keyboardCode = keyboardLine.slice(keyboardLine.indexOf("$('prompt').onkeydown="));
let presses = 0;
const keyboardNodes = {prompt: {}, send: {click(){presses++;}}};
vm.runInNewContext(keyboardCode, {$:id=>keyboardNodes[id]}, {timeout: 1500});
function keypress(key, shiftKey=false, isComposing=false, keyCode=13){
  const e = {key,shiftKey,isComposing,keyCode,preventDefault(){this.prevented=true}};
  keyboardNodes.prompt.onkeydown(e);
  return !!e.prevented;
}
assert.equal(keypress('Enter',false,true),false,'D01_IME_ENTER_SENT_PREMATURELY');
assert.equal(keypress('Enter',false,false,229),false,'D01_IME_LEGACY_ENTER_SENT');
assert.equal(keypress('Enter',true),false,'D01_SHIFT_ENTER_BLOCKED');
assert.equal(keypress('a'),false,'D01_TYPING_BLOCKED');
assert.equal(presses,0,'D01_COMPOSITION_MUST_NOT_SEND');
assert.equal(keypress('Enter'),true,'D01_NORMAL_ENTER_MUST_SEND');
assert.equal(presses,1,'D01_CHAT_SEND_ONCE');
console.log('D01 R8 SOURCE_ONLY PASS: compact panel scroll, IME-safe Enter, Shift+Enter, single send');
