'use strict';
// Executes the actual WebView2 Persona transition handler with a small DOM
// oracle. SOURCE_ONLY: does NOT claim Windows/WPF/owner-EXE acceptance.
const fs=require('node:fs'), path=require('node:path'), assert=require('node:assert/strict');
const html=fs.readFileSync(path.join(__dirname,'..','overrides','src','index.html'),'utf8');
const marker="case 'persona.changed':";
assert.equal(html.split(marker).length,2,'one original persona event owner');
const block=html.split(marker)[1].split("case 'settings.receipt':")[0];
assert.ok(block.includes("visiblePersona=nextPersona"),'native persona event not handled');
assert.ok(html.includes("if(pendingNote||pendingNoteDelete)"),'pending note write gate missing');
// Evaluate real original event code, not a reimplementation.
const handle=new Function('$','window','noteDrafts','state',`
let visiblePersona=state.visiblePersona,lastAnswer='previous private answer',responseBox={};
const v=state.v;const speechSynthesis={cancel(){state.cancelled=true}};
switch('persona.changed'){case 'persona.changed':${block}}
return {visiblePersona,lastAnswer,responseBox};
`);
const nodes={noteTitle:{value:'KV private draft'},noteText:{value:'KV private text'}};
for(const id of ['messages','history','notes','memoryResults','knowledgeResults']){
  nodes[id]={items:['KV private data'],replaceChildren(){this.items=[];}};
}
const $=id=>nodes[id],window={speechSynthesis:{}},noteDrafts=new Map();
let visiblePersona='KV';
function transition(persona){
 const state={visiblePersona,v:{persona},cancelled:false};
 const result=handle($,window,noteDrafts,state);
 visiblePersona=result.visiblePersona;
 return {state,result};
}
let first=transition('AM');
assert.equal(visiblePersona,'AM');
assert.deepEqual(noteDrafts.get('KV'),{title:'KV private draft',text:'KV private text'});
assert.equal(nodes.noteTitle.value,'');assert.equal(nodes.noteText.value,'');
for(const id of ['messages','history','notes','memoryResults','knowledgeResults'])assert.equal(nodes[id].items.length,0,id+' leaked');
assert.equal(first.result.lastAnswer,'');assert.equal(first.result.responseBox,null);assert.equal(first.state.cancelled,true);
// AM's draft cannot appear in KV, but must reappear upon switching back.
nodes.noteTitle.value='AM draft';nodes.noteText.value='AM text';
transition('KV');
assert.equal(nodes.noteTitle.value,'KV private draft');assert.equal(nodes.noteText.value,'KV private text');
transition('AM');
assert.equal(nodes.noteTitle.value,'AM draft');assert.equal(nodes.noteText.value,'AM text');
transition('unknown-persona');
assert.equal(visiblePersona,'AM');assert.equal(nodes.noteTitle.value,'AM draft');
console.log('D03 R8 SOURCE_ONLY native Persona DOM/draft regression PASS');
