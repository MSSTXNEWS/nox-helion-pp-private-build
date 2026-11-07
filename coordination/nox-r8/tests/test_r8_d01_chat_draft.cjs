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

/* D01_NATIVE_BRIDGE_THROW_NO_LOSS: execute the real production bridge and SEND handler.
   Even a dying WebView2 host must not discard a draft or leave SEND busy. */
const nativeBridgeLine = html.split('\n').find(line => line.startsWith('const $=id=>document.getElementById(id);const post='));
assert.ok(nativeBridgeLine, 'D01_NATIVE_POST_MISSING');
function nativeBridgeCase(webview, draft = 'Невыгруженный черновик') {
  const nodes = {status:{textContent:''}, prompt:{value:draft}, send:{}, streamHint:{textContent:''}, messages:{}};
  const emitted = [];
  const scope = {
    window: webview === null ? {} : {chrome:{webview}},
    document:{getElementById:id=>nodes[id]},
    entry:()=>{throw new Error('DRAFT_MUST_NOT_RENDER_IF_BRIDGE_FAILED')},
    nextChatId:()=> 'd01_native_bridge_failure_01',
    busy:false, activeChatId:null, responseBox:null, lastAnswer:'retained'
  };
  vm.runInNewContext(nativeBridgeLine + '\n' + code + '\n$("send").onclick();', scope, {timeout:1500});
  return {nodes,scope,emitted};
}
let disconnected = nativeBridgeCase(null);
assert.equal(disconnected.nodes.prompt.value, 'Невыгруженный черновик');
assert.equal(disconnected.scope.busy, false);
assert.equal(disconnected.scope.activeChatId, null);
assert.match(disconnected.nodes.status.textContent, /BRIDGE OFFLINE/);
disconnected = nativeBridgeCase({});
assert.equal(disconnected.scope.busy, false);
assert.equal(disconnected.nodes.prompt.value, 'Невыгруженный черновик');
let throwCount=0;
const rejected = nativeBridgeCase({postMessage:()=>{throwCount++;throw new Error('WebView2 detached')}});
assert.equal(throwCount,1,'D01_POST_MUST_NOT_RETRY_NATIVE_ACTION');
assert.equal(rejected.nodes.prompt.value,'Невыгруженный черновик');
assert.equal(rejected.scope.busy,false);
assert.equal(rejected.scope.activeChatId,null);
assert.match(rejected.nodes.status.textContent,/DISPATCH FAILED/);
assert.match(rejected.nodes.streamHint.textContent,/Черновик сохранён/);
console.log('D01 R8 SOURCE_ONLY PASS: native post missing/throw fail closed, no draft loss, no retry');


/* D01: execute the production route function with a compact/desktop scroll
   fixture. This checks user-visible navigation behavior, not native UIA. */
const routeStart = html.indexOf('function route(id){');
const routeEnd = html.indexOf("\ndocument.querySelectorAll('[data-route]')", routeStart);
assert.ok(routeStart > 0 && routeEnd > routeStart, 'D01_ORIGINAL_ROUTE_MISSING');
const actualRoute = html.slice(routeStart, routeEnd);
function routeAtWidth(compact) {
  const scroll = {scrollTop: 460}, title={textContent:''};
  const node = {
    dataset:{route:'core',panel:'core'},
    classList:{toggle(){}},
    setAttribute(){},removeAttribute(){}
  };
  const document = {
    querySelectorAll(sel) {
      if(sel === '.core[data-route]' || sel === '.panel[data-panel]') return [node];
      return [];
    },
    querySelector(sel){return sel === 'aside.side' ? scroll : null;}
  };
  const window = {matchMedia: () => ({matches:compact})};
  const post = () => {throw new Error('CORE_ROUTE_SHOULD_NOT_START_NATIVE_ACTION');};
  const run = new Function('document','window','$','post','headings',
    actualRoute + "\nreturn route('core');");
  assert.equal(run(document,window,()=>title,post,{core:'CORE / LIVE CHAT'}),true);
  assert.equal(title.textContent,'CORE / LIVE CHAT');
  return scroll.scrollTop;
}
assert.equal(routeAtWidth(true),0,'D01_COMPACT_ROUTE_MUST_REVEAL_NAVIGATION');
assert.equal(routeAtWidth(false),460,'D01_DESKTOP_ROUTE_MUST_PRESERVE_SCROLL');
console.log('D01 R8 SOURCE_ONLY PASS: compact route restores visible navigation; desktop unchanged');

/* D01_HIDDEN_PANEL_FOCUS: real route() handler contract; WebView2 UIA separately gated. */
const navLine=html.split('\n').find(s=>s.startsWith('function route(id){'));
assert.ok(navLine,'D01_REAL_ROUTE_MISSING');
const navIds=[...html.matchAll(/<button class="core[^"]*" data-route="([^"]+)"/g)].map(m=>m[1]);
assert.equal(navIds.length,8,'D01_COREID_NO_LOSS');
const navDoc={activeElement:null},title={textContent:''};
function node(data){
 const cls=new Set();
 return {dataset:data,classList:{toggle(k,on){on?cls.add(k):cls.delete(k)},contains:k=>cls.has(k)},
  setAttribute(k,v){this[k]=v},removeAttribute(k){delete this[k]},
  focus(){navDoc.activeElement=this},closest(){return this.parentPanel||null}};
}
const buttons=navIds.map(route=>node({route})),panels=navIds.map(panel=>node({panel}));
navDoc.querySelectorAll=s=>s==='.core[data-route]'?buttons:panels;
navDoc.querySelector=s=>buttons.find(b=>s==='button.core[data-route="'+b.dataset.route+'"]')||null;
const scope={document:navDoc,headings:Object.fromEntries(navIds.map(id=>[id,id.toUpperCase()])),
  $:()=>title,post:()=>true};
vm.runInNewContext(navLine,scope,{timeout:1500});
const child=node({});child.parentPanel=panels.find(p=>p.dataset.panel==='consciousness');
navDoc.activeElement=child;assert.equal(scope.route('core'),true);
assert.equal(navDoc.activeElement,buttons.find(b=>b.dataset.route==='core'),'D01_FOCUS_HIDDEN_PANEL');
assert.equal(buttons.find(b=>b.dataset.route==='core')['aria-current'],'page');
child.parentPanel=panels.find(p=>p.dataset.panel==='core');navDoc.activeElement=child;
scope.route('core');assert.equal(navDoc.activeElement,child,'D01_SAME_ROUTE_FOCUS_CHANGED');
navDoc.activeElement=buttons[0];scope.route('atlas');
assert.equal(navDoc.activeElement,buttons[0],'D01_NAV_FOCUS_CHANGED');
assert.equal(scope.route('unknown'),false,'D01_UNKNOWN_ROUTE_ALLOWED');
for(const id of navIds){assert.equal(scope.route(id),true);assert.equal(
 panels.find(p=>p.dataset.panel===id).classList.contains('active'),true);
 assert.equal(buttons.find(b=>b.dataset.route===id)['aria-current'],'page');}
console.log('D01 R8 SOURCE_ONLY PASS: hidden panel focus, eight routes, ARIA, keyboard preservation');


/* D01 compact quick-action accessibility: this SOURCE_ONLY contract is
   separate from WebView2's real computed-rectangle Windows receipt. */
const quickPanel = html.match(/<div class="quick">([\s\S]*?)<\/div>/)?.[1];
assert.ok(quickPanel, 'D01_ORIGINAL_QUICK_ACTIONS_MISSING');
assert.equal((quickPanel.match(/<button\b/g) || []).length, 5, 'D01_FIVE_QUICK_ACTIONS_NO_LOSS');
for (const label of ['CHAT','MODELS','LEARN','SETTINGS','✦ MAX'])
  assert.ok(quickPanel.includes(label), 'D01_QUICK_LABEL_LOST_' + label);
assert.match(html, /@media\(max-width:1000px\)\{\.quick \.action\{min-height:44px;min-width:44px\}\}/,
  'D01_COMPACT_TOUCH_TARGET_44_SOURCE_HOLD');
const nativePaths = [
  path.resolve(__dirname, 'src/MainWindow.xaml.cs'),
  path.resolve(__dirname, '../overrides/src/MainWindow.xaml.cs')
];
const nativePath = nativePaths.find(candidate => fs.existsSync(candidate));
assert.ok(nativePath, 'D01_NATIVE_SOURCE_MISSING');
const nativeSource = fs.readFileSync(nativePath, 'utf8');
assert.match(nativeSource, /rect\.width >= 44 && rect\.height >= 44/,
  'D01_COMPACT_TOUCH_TARGET_44_NATIVE_GATE_HOLD');
assert.match(nativeSource, /new\[\] \{ 320, 390, 800 \}/,
  'D01_COMPACT_PHYSICAL_VIEWPORT_GATE_MISSING');
console.log('D01 SOURCE_ONLY PASS: five original buttons, compact 44px hit targets, native physical gate');

/* D01_NONCHAT_SEARCH_IME_GUARD: execute the original R8 keyboard handlers, not a rewrite.
   SOURCE_ONLY: native WebView2/UIA remains a separate physical gate. */
for (const [field,action] of [['knowledgeQuery','knowledgeSearch'],['memoryQuery','memorySearch']]) {
  const line=html.split('\n').find(s=>s.includes("$('"+field+"').onkeydown="));
  assert.ok(line,'D01_SEARCH_KEYBOARD_SOURCE_MISSING_'+field);
  const start=line.indexOf("$('"+field+"').onkeydown=");
  const end=line.indexOf('};',start);
  assert.ok(end>start,'D01_SEARCH_KEYBOARD_HANDLER_INVALID_'+field);
  const handlerSrc=line.slice(start,end+2);
  const nodes={[field]:{},[action]:{calls:0,click(){this.calls++}}};
  vm.runInNewContext(handlerSrc,{$:id=>nodes[id]},{timeout:1500});
  function press(extra={}) {
    let prevented=0;
    nodes[field].onkeydown({key:'Enter',keyCode:13,isComposing:false,shiftKey:false,repeat:false,
      preventDefault(){prevented++},...extra});
    return prevented;
  }
  assert.equal(press({isComposing:true}),0,'D01_COMPOSITION_HANDLED_'+field);
  assert.equal(press({keyCode:229}),0,'D01_IME_229_HANDLED_'+field);
  assert.equal(press({shiftKey:true}),0,'D01_SHIFT_ENTER_HANDLED_'+field);
  assert.equal(press({repeat:true}),1,'D01_REPEAT_PREVENT_DEFAULT_'+field);
  assert.equal(nodes[action].calls,0,'D01_PREMATURE_SEARCH_'+field);
  assert.equal(press(),1,'D01_REAL_ENTER_DEFAULT_'+field);
  press({key:'Escape'});
  assert.equal(nodes[action].calls,1,'D01_EXACTLY_ONE_SEARCH_'+field);
}
console.log('D01 SOURCE_ONLY PASS: knowledge/memory keyboard IME, repeat, Enter');

/* D01: real route + persona.changed handlers, scoped SQLite memory UI.
   This executes production JavaScript; actual owner Windows UIA remains HOLD. */
{
  const routeLine = html.split('\n').find(x => x.startsWith('function route(id){'));
  assert.ok(routeLine, 'D01_PERSONA_ROUTE_MISSING');
  const sent = [], title = {textContent:''};
  const navDoc = {activeElement:null,querySelectorAll:()=>[],querySelector:()=>null};
  const routeContext = {document:navDoc,window:{matchMedia:()=>({matches:false})},
    $:()=>title,post:type=>sent.push(type),headings:{reflection:'REFLECTION / HISTORY'}};
  vm.runInNewContext(routeLine + "\nroute('reflection');",routeContext,{timeout:1500});
  assert.deepEqual(sent,['history','notes.list','knowledge.stats'],
    'D01_REFLECTION_NOTES_REFRESH_MISSING');
  const changedLine = html.split('\n').find(x=>x.trim().startsWith("case 'persona.changed':"));
  assert.ok(changedLine,'D01_PERSONA_CHANGE_HANDLER_MISSING');
  const ids = ['messages','history','notes','memoryResults','knowledgeResults'];
  const elements = Object.fromEntries(ids.map(id=>[id,{clears:0,
    replaceChildren(){this.clears++;}}]));
  const eventContext = {$:id=>elements[id],window:{}};
  const outcome=vm.runInNewContext(
    "let lastAnswer='previous persona secret';let responseBox={};"+
    "switch('persona.changed'){"+changedLine+"}"+
    "({lastAnswer,responseBox})",eventContext,{timeout:1500});
  for(const id of ids)
    assert.equal(elements[id].clears,1,'D01_PERSONA_STALE_PRIVATE_VIEW_'+id);
  assert.equal(outcome.lastAnswer,'','D01_PERSONA_OLD_REPLY_NOT_RESET');
  assert.equal(outcome.responseBox,null,'D01_PERSONA_OLD_STREAM_NOT_RESET');
}
console.log('D01 SOURCE_ONLY PASS: reflection notes refresh and PersonaID memory view isolation');
