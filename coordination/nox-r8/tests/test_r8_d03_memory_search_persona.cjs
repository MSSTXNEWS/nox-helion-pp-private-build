'use strict';
// D03 exact production MEMORY.SEARCH WPF/WebView2 owner protocol, SOURCE_ONLY.
const a=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..');
const cs=fs.readFileSync(path.join(root,'overrides/src/MainWindow.xaml.cs'),'utf8');
const html=fs.readFileSync(path.join(root,'overrides/src/index.html'),'utf8');
const native=cs.slice(cs.indexOf('case "memory.search":'),cs.indexOf('case "knowledge.search":'));
a.match(native,/ValidWriteRequestId\(requestId\)/);
a.match(native,/string persona = ActivePersona\(\)/);
a.match(native,/new \{ persona, requestId, rows = SearchMemory\(Text\("query"\), persona\) \}/);
a.match(native,/Send\("memory.denied"/);
const reader=cs.slice(cs.indexOf('private object SearchMemory('),cs.indexOf('private object ReadTasks('));
a.match(reader,/SearchMemory\(string query, string persona\)/);
a.match(reader,/WHERE persona=\$persona/);
a.match(reader,/cmd\.Parameters\.AddWithValue\("\$persona", persona\)/);
a.ok(!reader.includes('ActivePersona()'));
const lo=html.indexOf("case 'memory':"),hi=html.indexOf("case 'notes':",lo);
a.ok(lo>=0&&hi>lo);
const body=html.slice(lo,hi);
const handle=new Function('type','v','visiblePersona','pendingMemorySearch','$','entry',
  'switch(type){'+body+'default:break;}return pendingMemorySearch;');
function render(type,v,p,owner){
  const box={items:['SENTINEL'],textContent:'OLD',
    replaceChildren(){this.items=[];this.textContent='';}};
  const state=handle(type,v,owner,p,()=>box,(b,t)=>b.items.push(t));
  return {box,state};
}
const rows=[{prompt:'KV SECRET',answer:'PRIVATE',timestamp:'T'}];
const pending={requestId:'REQ_12345678',persona:'KV'};
a.equal(render('memory',{persona:'KV',requestId:pending.requestId,rows},pending,'AM').box.items[0],'SENTINEL');
a.equal(render('memory',rows,pending,'KV').box.items[0],'SENTINEL');
a.equal(render('memory',{persona:'KV',requestId:'OLD_12345678',rows},pending,'KV').box.items[0],'SENTINEL');
a.equal(render('memory',{persona:'KV',requestId:pending.requestId,rows},null,'KV').box.items[0],'SENTINEL');
a.equal(render('memory',{persona:'KV',requestId:pending.requestId,rows},pending,'KV').box.items[0],'KV SECRET\n\nPRIVATE');
const denied=render('memory.denied',{requestId:pending.requestId,reason:'NOX_MEMORY_READ_HOLD'},pending,'KV');
a.equal(denied.state,null);a.equal(denied.box.textContent,'NOX_MEMORY_READ_HOLD');
const a0=html.indexOf("$('memorySearch').onclick="),a1=html.indexOf("$('memoryQuery').onkeydown",a0);
a.ok(a0>=0&&a1>a0);
const runClick=new Function('$','post','nextChatId','visiblePersona',
  'let pendingMemorySearch=null;'+html.slice(a0,a1)+
  "$('memorySearch').onclick();return pendingMemorySearch;");
function click(persona){
 const nodes={memorySearch:{},memoryQuery:{value:'прИвЕт'},memoryResults:{textContent:'',replaceChildren(){}}},posts=[];
 const state=runClick(id=>nodes[id],(type,v)=>{posts.push({type,v});return true;},()=>pending.requestId,persona);
 return {state,posts};
}
a.equal(click(null).posts.length,0);
const sent=click('KV');
a.equal(sent.posts.length,1);a.equal(sent.posts[0].type,'memory.search');
a.equal(sent.posts[0].v.requestId,pending.requestId);a.equal(sent.state.persona,'KV');
a.match(html.slice(html.indexOf("case 'persona.changed':"),html.indexOf("case 'settings.receipt':")),/pendingMemorySearch=null/);
console.log('D03 SOURCE_ONLY memory search Persona/request V8 PASS');