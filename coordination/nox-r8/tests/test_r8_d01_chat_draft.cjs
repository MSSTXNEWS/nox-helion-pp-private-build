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
  const draftIds=['noteTitle','noteText','memoryQuery','knowledgeQuery','prompt','taskInput'];
  const oldDraft={
    noteTitle:'KV unsaved title',noteText:'KV unsaved note',
    memoryQuery:'KV memory query',knowledgeQuery:'KV knowledge query',
    prompt:'KV unsent chat prompt',taskInput:'KV unsent atlas task'
  };
  const elements = Object.fromEntries(ids.map(id=>[id,{clears:0,
    replaceChildren(){this.clears++;}}]));
  for(const id of draftIds)elements[id]={value:oldDraft[id]};
  const eventContext = {$:id=>elements[id],window:{},
    v:{persona:'AM'},committedSettings:{persona:'KV'},personaDrafts:new Map()};
  const draftStart=html.indexOf('function switchPersonaDrafts(next){');
  const draftEnd=html.indexOf('\nfunction route(id){',draftStart);
  assert.ok(draftStart>0&&draftEnd>draftStart,'D01_ORIGINAL_PERSONA_DRAFT_HANDLER_MISSING');
  vm.runInNewContext(html.slice(draftStart,draftEnd),eventContext,{timeout:1500});
  const outcome=vm.runInNewContext(
    "let lastAnswer='previous persona secret';let responseBox={};"+
    "switch('persona.changed'){"+changedLine+"}"+
    "({lastAnswer,responseBox})",eventContext,{timeout:1500});
  for(const id of ids)
    assert.equal(elements[id].clears,1,'D01_PERSONA_STALE_PRIVATE_VIEW_'+id);
  assert.equal(outcome.lastAnswer,'','D01_PERSONA_OLD_REPLY_NOT_RESET');
  assert.equal(outcome.responseBox,null,'D01_PERSONA_OLD_STREAM_NOT_RESET');
  for(const id of draftIds){
    assert.equal(elements[id].value,'','D01_FOREIGN_PERSONA_DRAFT_VISIBLE_'+id);
    assert.equal(eventContext.personaDrafts.get('KV')[id],oldDraft[id],
      'D01_UNSAVED_DRAFT_LOST_'+id);
  }
  eventContext.committedSettings.persona='AM';
  eventContext.v={persona:'KV'};
  for(const id of draftIds)elements[id].value='AM private '+id;
  vm.runInNewContext("switch('persona.changed'){"+changedLine+"}",eventContext,{timeout:1500});
  for(const id of draftIds){
    assert.equal(elements[id].value,oldDraft[id],'D01_KV_DRAFT_RESTORE_'+id);
    assert.equal(eventContext.personaDrafts.get('AM')[id],'AM private '+id,
      'D01_AM_DRAFT_KEEP_'+id);
  }
  eventContext.committedSettings.persona='KV';
  eventContext.v={persona:'KV'};
  elements.noteTitle.value='KV revised unsaved';
  vm.runInNewContext("switch('persona.changed'){"+changedLine+"}",eventContext,{timeout:1500});
  assert.equal(elements.noteTitle.value,'KV revised unsaved','D01_SAME_PERSONA_DRAFT_NO_LOSS');
}
console.log('D01 SOURCE_ONLY PASS: reflection notes refresh and PersonaID memory view isolation');

/* D01_GLOBAL_IME_SHORTCUT_GUARD: original document handler under the actual
   R8 WebView2 source. SOURCE_ONLY; not Windows UIA/physical STOP evidence. */
{
  const sourceStart=html.indexOf("document.addEventListener('keydown',e=>");
  const sourceEnd=html.indexOf("\nroute('consciousness');",sourceStart);
  assert.ok(sourceStart>0 && sourceEnd>sourceStart,'D01_GLOBAL_KEY_HANDLER_MISSING');
  let keyHandler, stops=0, routes=0, focuses=0;
  const elements={
    stop:{click(){stops++}},
    prompt:{focus(){focuses++}}
  };
  const keyboardDocument={addEventListener(type,handler){
    if(type==='keydown')keyHandler=handler;
  }};
  vm.runInNewContext(html.slice(sourceStart,sourceEnd),{
    document:keyboardDocument,$:id=>elements[id],route:()=>{routes++},
    busy:true,activeChatId:'d01_exact_active_request'
  },{timeout:1500});
  assert.equal(typeof keyHandler,'function','D01_GLOBAL_LISTENER_NOT_REGISTERED');
  function press(key,extra={}){
    let handled=0;
    keyHandler({key,keyCode:0,ctrlKey:false,altKey:false,metaKey:false,
      shiftKey:false,isComposing:false,repeat:false,defaultPrevented:false,
      preventDefault(){handled++},...extra});
    return handled;
  }
  assert.equal(press('Escape',{isComposing:true}),0,'D01_IME_ESCAPE_INTERCEPTED');
  assert.equal(press('Escape',{keyCode:229}),0,'D01_LEGACY_IME_ESCAPE_INTERCEPTED');
  assert.equal(press('Escape',{repeat:true}),0,'D01_REPEAT_ESCAPE_INTERCEPTED');
  assert.equal(press('Escape',{defaultPrevented:true}),0,'D01_HANDLED_ESCAPE_INTERCEPTED');
  assert.equal(press('k',{ctrlKey:true,isComposing:true}),0,'D01_IME_CTRL_K_INTERCEPTED');
  assert.equal(press('k',{ctrlKey:true,altKey:true}),0,'D01_ALT_CTRL_K_INTERCEPTED');
  assert.equal(press('k',{ctrlKey:true,shiftKey:true}),0,'D01_SHIFT_CTRL_K_INTERCEPTED');
  assert.equal(press('k',{ctrlKey:true,repeat:true}),0,'D01_REPEAT_CTRL_K_INTERCEPTED');
  assert.deepEqual([stops,routes,focuses],[0,0,0],'D01_IME_MUST_NOT_DISPATCH');
  assert.equal(press('Escape'),1,'D01_REAL_ESCAPE_MUST_STOP');
  assert.equal(press('k',{ctrlKey:true}),1,'D01_REAL_CTRL_K_MUST_ROUTE');
  assert.deepEqual([stops,routes,focuses],[1,1,1],'D01_EXACTLY_ONE_NATIVE_STOP_AND_ROUTE');
}
console.log('D01 SOURCE_ONLY PASS: global IME-safe Escape/STOP and Ctrl+K');

/* D01_COREID_KEYBOARD_IME_MODIFIERS: actual production handler.
   Prevent IME, assistive/modified shortcuts, and repeats from initiating
   native route/SQLite refreshes; preserve eight normal keyboard routes.
   SOURCE_ONLY; Windows UIA remains a separate physical acceptance gate. */
{
  const navIds=[...html.matchAll(/<button class="core[^"]*" data-route="([^"]+)"/g)].map(m=>m[1]);
  assert.equal(navIds.length,8,'D01_COREID_KEYBOARD_EIGHT_REQUIRED');
  const navLine=html.split('\n').find(x=>x.startsWith('const coreRouteButtons='));
  assert.ok(navLine,'D01_COREID_NATIVE_HANDLER_MISSING');
  const moved=[],called=[];
  const buttons=navIds.map(route=>({
    dataset:{route},addEventListener(event,fn){if(event==='keydown')this.fn=fn;},
    focus(){moved.push(route)}
  }));
  vm.runInNewContext(navLine,{
    document:{querySelectorAll:()=>buttons},route:id=>called.push(id)
  },{timeout:1500});
  function key(index,name,extra={}){
    let consumed=0;
    buttons[index].fn({key:name,repeat:false,isComposing:false,keyCode:0,
      ctrlKey:false,altKey:false,metaKey:false,shiftKey:false,
      defaultPrevented:false,preventDefault(){consumed++},...extra});
    return consumed;
  }
  for(const extra of [{ctrlKey:true},{altKey:true},{shiftKey:true},{metaKey:true},
      {isComposing:true},{keyCode:229},{repeat:true},{defaultPrevented:true}]){
    assert.equal(key(0,'ArrowRight',extra),0,'D01_NAV_STOLEN_COMPOSITION_OR_SHORTCUT');
  }
  assert.deepEqual(called,[],'D01_UNEXPECTED_NATIVE_REFRESH');
  assert.deepEqual(moved,[],'D01_UNEXPECTED_KEYBOARD_FOCUS');
  assert.equal(key(0,'ArrowRight'),1);
  assert.equal(key(0,'ArrowLeft'),1);
  assert.equal(key(4,'Home'),1);
  assert.equal(key(4,'End'),1);
  assert.deepEqual(called,[navIds[1],navIds[7],navIds[0],navIds[7]],
    'D01_EIGHT_COREID_KEYBOARD_NO_LOSS');
  assert.deepEqual(moved,called,'D01_COREID_FOCUS_NOT_FOLLOWING_ROUTE');
}
console.log('D01 SOURCE_ONLY PASS: 8 CoreID focus, IME/modified/repeat navigation guard');


/* D01_CHAT_FAIL_RECOVERY: production WebView2 SEND/complete handlers.
   A failed or owner-stopped Ollama turn cannot silently discard the unsaved
   prompt; a new draft typed during streaming must not be overwritten.
   SOURCE_ONLY evidence, not local Qwen or WPF runtime acceptance. */
{
  const start=html.indexOf("$('send').onclick=()=>");
  const finish=html.indexOf("\n$('stop').onclick=",start);
  const completeStart=html.indexOf("case 'complete':");
  const completeEnd=html.indexOf("\ncase 'error':",completeStart);
  assert.ok(start>0&&finish>start&&completeStart>0&&completeEnd>completeStart,
    'D01_ORIGINAL_CHAT_RECOVERY_HANDLERS_MISSING');
  const sendHandler=html.slice(start,finish);
  const completeHandler=html.slice(completeStart,completeEnd);
  function scenario(result,newDraft=''){
    const raw="  Сохранить вопрос после STOP  \n";
    const nodes={send:{},prompt:{value:raw},streamHint:{textContent:''},
      messages:{},generation:{classList:{remove(){}}}};
    const machine=vm.runInNewContext(
      "let responseBox=null,lastAnswer='',busy=false,activeChatId=null,pendingChatDraft=null;"+
      sendHandler+
      "\nfunction finishTurn(v){switch('complete'){"+completeHandler+"}}\n"+
      "({send:()=>$('send').onclick(),finishTurn,state:()=>({busy,pendingChatDraft})})",
      {$:id=>nodes[id],post:()=>true,nextChatId:()=> 'd01_real_request',
        entry:()=>({lastChild:{textContent:''}}),
        window:{noxVisual:{setEnergy(){}}}},
      {timeout:1500});
    machine.send();
    assert.equal(nodes.prompt.value,'','D01_ORIGINAL_SEND_MUST_CLEAR_ACTIVE_COMPOSER');
    nodes.prompt.value=newDraft;
    machine.finishTurn({requestId:'d01_real_request',...result});
    assert.equal(machine.state().busy,false,'D01_CHAT_BUSY_AFTER_COMPLETION');
    assert.equal(machine.state().pendingChatDraft,null,'D01_RETRY_BUFFER_NOT_RELEASED');
    return {value:nodes.prompt.value,hint:nodes.streamHint.textContent,raw};
  }
  const failure=scenario({ok:false,stopped:false});
  assert.equal(failure.value,failure.raw,'D01_OLLAMA_FAILURE_DISCARDED_UNSAVED_PROMPT');
  assert.match(failure.hint,/восстановлен/,'D01_RECOVERY_NO_USER_MESSAGE');
  const stopped=scenario({ok:false,stopped:true});
  assert.equal(stopped.value,stopped.raw,'D01_OWNER_STOP_DISCARDED_UNSAVED_PROMPT');
  assert.match(stopped.hint,/остановлен/,'D01_STOP_HINT_LOST');
  assert.equal(scenario({ok:true,stopped:false}).value,'',
    'D01_SQLITE_SUCCESS_MUST_NOT_RESTORE_SENT_PROMPT');
  assert.equal(scenario({ok:false,stopped:false},'Новый несохранённый текст').value,
    'Новый несохранённый текст','D01_FAILURE_OVERWROTE_NEW_COMPOSER');
}
console.log('D01 SOURCE_ONLY PASS: Qwen failed/STOP retry with original input, SQLite ACK, and concurrent draft');

/* D01 2026-11-07: production receipt source must not erase another PersonaID's
   identical unsent task/note draft. Also cover SQLite startup persona hydration.
   SOURCE_ONLY: actual owner Windows/SQLite E2E requires frozen EXE SHA. */
{
  const swStart=html.indexOf('function switchPersonaDrafts(next){');
  const swEnd=html.indexOf('\nfunction route(id){',swStart);
  const apStart=html.indexOf('function applyCommittedSettings(v){');
  const apEnd=html.indexOf('\nfunction saveSetting',apStart);
  const taskAck=html.split('\n').find(line=>line.startsWith("case 'tasks.add.receipt':"));
  const noteAck=html.split('\n').find(line=>line.startsWith("case 'notes.add.receipt':"));
  assert.ok(swStart>0 && swEnd>swStart && apStart>0 && apEnd>apStart && taskAck && noteAck,
    'D01_PERSONA_RECEIPT_ORIGINAL_SOURCE_MISSING');
  const realSource = `
    const nodes=Object.fromEntries(['noteTitle','noteText','memoryQuery','knowledgeQuery',
      'prompt','taskInput','persona','performance'].map(id=>[id,{value:''}]));
    for(const id of ['taskAdd','noteAdd'])nodes[id]={disabled:true};
    nodes.status={textContent:''};nodes.personaStatus={textContent:''};
    nodes.useContext={checked:true};nodes.reduceMotion={checked:false};
    const $=id=>{if(!nodes[id])throw Error('MISSING_'+id);return nodes[id]};
    const window={noxVisual:{setMode(){}}};
    const document={body:{classList:{toggle(){}}}};
    let committedSettings={persona:'KV'},visibleDraftPersona='KV';
    let pendingTask={requestId:'task-kv',text:'SAME',persona:'KV'};
    let pendingNote={requestId:'note-kv',title:'SAME',content:'SAME',persona:'KV'};
    const personaDrafts=new Map();
    ${html.slice(swStart,swEnd)}
    ${html.slice(apStart,apEnd)}
    nodes.noteTitle.value='KV-TITLE';nodes.noteText.value='KV-TEXT';
    switchPersonaDrafts('AM');
    if(nodes.noteTitle.value!=='')throw Error('D01_FOREIGN_DRAFT_VISIBLE');
    nodes.taskInput.value='SAME';nodes.noteTitle.value='SAME';nodes.noteText.value='SAME';
    let v={requestId:'task-kv',saved:true};
    switch('tasks.add.receipt'){${taskAck}}
    v={requestId:'note-kv',saved:true};
    switch('notes.add.receipt'){${noteAck}}
    if([nodes.taskInput.value,nodes.noteTitle.value,nodes.noteText.value]
      .some(x=>x!=='SAME'))throw Error('D01_FOREIGN_RECEIPT_ERASED_UNSENT_DRAFT');
    if(pendingTask||pendingNote||nodes.taskAdd.disabled||nodes.noteAdd.disabled)
      throw Error('D01_PENDING_NOT_RELEASED');
    pendingTask={requestId:'task-am',text:'SAME',persona:'AM'};
    pendingNote={requestId:'note-am',title:'SAME',content:'SAME',persona:'AM'};
    nodes.taskAdd.disabled=true;nodes.noteAdd.disabled=true;
    v={requestId:'task-am',saved:true};switch('tasks.add.receipt'){${taskAck}}
    v={requestId:'note-am',saved:true};switch('notes.add.receipt'){${noteAck}}
    if([nodes.taskInput.value,nodes.noteTitle.value,nodes.noteText.value]
      .some(x=>x!==''))throw Error('D01_OWN_RECEIPT_NOT_CLEARED');
    nodes.prompt.value='AM private chat';
    applyCommittedSettings({persona:'LA',performance:'BALANCED',context:'on',motion:'on'});
    if(visibleDraftPersona!=='LA'||nodes.prompt.value!==''||
      personaDrafts.get('AM').prompt!=='AM private chat')
      throw Error('D01_SETTINGS_PERSONA_HYDRATION_FAILED');
    return 'PASS';
  `;
  assert.equal(vm.runInNewContext(realSource,{}, {timeout:1500}),'PASS',
    'D01_PERSONA_PENDING_RECEIPT_NO_LOSS_SOURCE_HOLD');
  console.log('D01 SOURCE_ONLY PASS: foreign PersonaID ACK isolation, own ACK clear, startup SQLite persona');
}
