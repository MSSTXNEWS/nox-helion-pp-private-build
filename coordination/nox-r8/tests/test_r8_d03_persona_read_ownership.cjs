'use strict';
// D03: run original WPF-source protocol assertions and original WebView2 handlers.
// SOURCE_ONLY regression. Never read or modify the owner's SQLite.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const cs = fs.readFileSync(path.join(root, 'overrides/src/MainWindow.xaml.cs'),'utf8');
const html = fs.readFileSync(path.join(root, 'overrides/src/index.html'),'utf8');
assert.match(cs,/private void SendPersonaHistory\(\)/);
assert.match(cs,/Send\("history", new \{ persona, rows = ReadHistory\(persona\) \}\)/);
assert.match(cs,/Send\("notes", new \{ persona, rows = ReadNotes\(persona\) \}\)/);
for (const [method,next] of [['ReadHistory(string persona)','// R8 D03: SQLite lower()'],['ReadNotes(string persona)','private long AddNote(']]) {
  const start=cs.indexOf('private object '+method), end=cs.indexOf(next,start);
  assert.ok(start>=0&&end>start,'native reader found');
  assert.match(cs.slice(start,end),/cmd\.Parameters\.AddWithValue\("\$persona", persona\)/);
}
assert.ok(!cs.includes('Send("history", ReadHistory());'));
assert.ok(!cs.includes('Send("notes", ReadNotes());'));
function body(name,next) {
  const a=html.indexOf("case '"+name+"':"),b=html.indexOf("case '"+next+"':",a);
  assert.ok(a>=0&&b>a);return html.slice(a,b);
}
function render(type,v,visiblePersona) {
  const box={children:['sentinel'],textContent:'UNMODIFIED',
    replaceChildren(){this.children=[];this.textContent=''},
    append(...items){this.children.push(...items)}};
  const element=(tag,text,cls)=>({tag,textContent:text,className:cls,children:[],
    append(...items){this.children.push(...items)}});
  // Execute the exact original handlers, not a rewritten copy.
  const run=new Function('type','v','visiblePersona','$','entry','element',
    'pendingNoteDelete','noteDeleteUncertain','pendingNote','nextChatId','post','document',
    'switch(type){'+body('history','tasks')+body('notes','notes.delete.receipt')+'default:break;}');
  run(type,v,visiblePersona,()=>box,(target,text,title)=>target.children.push({text,title}),
    element,false,false,null,()=> 'req',()=>true,{querySelectorAll:()=>[]});
  return box;
}
const history=[{prompt:'KV PRIVATE',answer:'SECRET',timestamp:'2026-11-07'}];
const notes=[{id:44,title:'KV PRIVATE',content:'SECRET',timestamp:'2026-11-07'}];
for (const [type,rows] of [['history',history],['notes',notes]]) {
  assert.equal(render(type,{persona:'KV',rows},'AM').children[0],'sentinel',
    'stale KV data must not render under AM');
  assert.equal(render(type,rows,'AM').children[0],'sentinel',
    'legacy unscoped arrays must fail closed');
  assert.notEqual(render(type,{persona:'AM',rows},'AM').children[0],'sentinel',
    'current Persona data remains available');
}
const from=html.indexOf('function applyCommittedSettings('),to=html.indexOf('function saveSetting(',from);
assert.ok(from>=0&&to>from);
const posts=[];
const hydrate=new Function('post','$','document','window',
  'let visiblePersona=null,committedSettings={};'+html.slice(from,to)+
  "applyCommittedSettings({persona:'AM',performance:'BALANCED',context:'on',motion:'on'});return visiblePersona;");
assert.equal(hydrate(type=>posts.push(type),()=>({value:null,checked:false}),
  {body:{classList:{toggle(){}}}},{noxVisual:{setMode(){}}}),'AM');
assert.deepEqual(posts,['history','notes.list'],'bootstrap must requery after Persona binding');
console.log('D03 SOURCE_ONLY Persona-owned HISTORY/NOTES: original handlers and hydration PASS');
