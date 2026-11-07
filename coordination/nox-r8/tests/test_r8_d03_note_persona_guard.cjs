'use strict';
// D03 SOURCE_ONLY: original WPF source contract + original WebView2 click/receipt handler.
// Does not imply Windows EXE, real SQLite, or owner-PC acceptance.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.join(__dirname,'..','overrides','src');
const cs=fs.readFileSync(path.join(root,'MainWindow.xaml.cs'),'utf8');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const native=cs.slice(cs.indexOf('private void HandleNoteAdd('),cs.indexOf('private void HandleSettingsPut('));
assert.ok(cs.includes('case "notes.add": HandleNoteAdd(Text("title"), Text("content"), Text("requestId"), Text("persona")); break;'));
assert.ok(native.includes('string requestedPersona'));
assert.ok(native.includes('NOX_NOTE_PERSONA_CHANGED_HOLD'));
assert.ok(native.includes('string.Equals(requestedPersona, persona, StringComparison.Ordinal)'));
assert.ok(native.indexOf('string.Equals(requestedPersona, persona, StringComparison.Ordinal)')<native.indexOf('writeAttempted = true;'));
assert.ok(native.indexOf('writeAttempted = true;')<native.indexOf('long id = AddNote('));
const click=html.slice(html.indexOf("$('noteAdd').onclick="),html.indexOf("$('feedbackUp').onclick="));
const cases=html.slice(html.indexOf("case 'notes.add.receipt':"),html.indexOf("case 'system':"));
assert.ok(click.includes("post('notes.add',{title,content,persona,requestId})"));
function app(){
  const nodes={noteAdd:{disabled:false},noteTitle:{value:'private title'},noteText:{value:'KV private note'},status:{textContent:''}};
  const sent=[];let seq=0;
  const factory=new Function('$','post','nextChatId',
    'let pendingNote=null,noteAddUncertain=false,visiblePersona=null;' + click +
    'function receive(type,v){switch(type){' + cases + '}}' +
    'return {click:()=> $("noteAdd").onclick(),receive,persona:p=>visiblePersona=p};');
  const owner=factory(id=>nodes[id],(type,data)=>{sent.push({type,...data});return true},()=>('req_'+(++seq)));
  return {nodes,sent,owner};
}
{
  const {nodes,sent,owner}=app();
  owner.click();assert.equal(sent.length,0,'no IPC before persona hydration');
  assert.equal(nodes.status.textContent,'NOX_NOTE_PERSONA_NOT_READY_HOLD');
  owner.persona('KV');owner.click();assert.equal(sent.length,1);
  assert.equal(sent[0].type,'notes.add');assert.equal(sent[0].persona,'KV');
  owner.persona('AM');nodes.noteTitle.value='AM title';nodes.noteText.value='AM private note';
  owner.receive('notes.add.receipt',{requestId:sent[0].requestId,saved:true});
  assert.equal(nodes.noteTitle.value,'AM title');assert.equal(nodes.noteText.value,'AM private note');
}
{
  const {nodes,sent,owner}=app();owner.persona('KW');owner.click();
  assert.equal(sent[0].persona,'KW');
  owner.receive('notes.add.denied',{requestId:sent[0].requestId,reason:'NOX_NOTE_PERSONA_CHANGED_HOLD'});
  assert.equal(nodes.noteAdd.disabled,false);
  assert.equal(nodes.noteText.value,'KV private note');
}
console.log('D03 SOURCE_ONLY note Persona mismatch guard: original handler PASS');
