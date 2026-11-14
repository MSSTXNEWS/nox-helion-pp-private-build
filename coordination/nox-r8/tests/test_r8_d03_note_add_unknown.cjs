'use strict';
// D03 original WPF source + original WebView2 dispatch replay check.
// SOURCE_ONLY: not a physical Windows EXE or owner data acceptance.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const dir=path.join(__dirname,'..','overrides','src');
const cs=fs.readFileSync(path.join(dir,'MainWindow.xaml.cs'),'utf8');
const html=fs.readFileSync(path.join(dir,'index.html'),'utf8');
const native=cs.slice(cs.indexOf('private void HandleNoteAdd('),cs.indexOf('private void HandleSettingsPut('));
for(const required of ['bool writeAttempted = false;','writeAttempted = true;',
  'NOX_NOTE_ADD_COMMIT_UNKNOWN_HOLD','Send("notes.add.unknown"',
  'Send("notes.add.receipt"'])assert.ok(native.includes(required),required);
assert.ok(native.indexOf('writeAttempted = true;')<native.indexOf('long id = AddNote('));
assert.ok(native.indexOf('Send("notes.add.receipt"')<native.indexOf('Send("notes", ReadNotes())'));
assert.ok(native.indexOf('if (writeAttempted)')>native.indexOf('Send("notes.add.receipt"'));
assert.ok(!native.includes('catch (SqliteException) { Send("notes.add.denied"'));
const click=html.slice(html.indexOf("$('noteAdd').onclick="),html.indexOf("$('feedbackUp').onclick="));
const cases=html.slice(html.indexOf("case 'notes.add.receipt':"),html.indexOf("case 'system':"));
assert.ok(click.includes('noteAddUncertain')&&cases.includes("case 'notes.add.unknown':"));
function app(){
 const nodes={noteAdd:{disabled:false},noteTitle:{value:'private title'},noteText:{value:'private text'},status:{textContent:''}},sent=[];let seq=0;
 const owner=new Function('$','post','nextChatId',`let pendingNote=null,noteAddUncertain=false,visibleDraftPersona='KV';${click} function receive(type,v){switch(type){${cases}}}return {click:()=> $('noteAdd').onclick(),receive,pending:()=>pendingNote,uncertain:()=>noteAddUncertain};`)(
    id=>nodes[id],(type,data)=>{sent.push({type,...data});return true},()=>('owner-'+(++seq)));
 return {nodes,sent,owner};
}
{
 const {nodes,sent,owner}=app();owner.click();const req=sent[0].requestId;
 owner.receive('notes.add.unknown',{requestId:'foreign',reason:'NOX_NOTE_ADD_COMMIT_UNKNOWN_HOLD'});
 assert.ok(owner.pending(),'foreign ACK cannot settle');
 owner.receive('notes.add.unknown',{requestId:req,reason:'NOX_NOTE_ADD_COMMIT_UNKNOWN_HOLD'});
 assert.equal(owner.pending(),null);assert.equal(owner.uncertain(),true);
 assert.equal(nodes.noteAdd.disabled,true);
 assert.equal(nodes.noteText.value,'private text');
 owner.click();assert.equal(sent.filter(x=>x.type==='notes.add').length,1);
 assert.equal(sent.filter(x=>x.type==='notes.list').length,1);
}
{
 const {nodes,sent,owner}=app();owner.click();
 owner.receive('notes.add.denied',{requestId:sent[0].requestId,reason:'NOX_NOTE_VALIDATION_HOLD'});
 assert.equal(nodes.noteAdd.disabled,false);owner.click();
 assert.equal(sent.filter(x=>x.type==='notes.add').length,2);
}
{
 const {nodes,sent,owner}=app();owner.click();
 owner.receive('notes.add.receipt',{requestId:sent[0].requestId,saved:true});
 assert.equal(nodes.noteAdd.disabled,false);
 assert.equal(nodes.noteText.value,'');
}
console.log('D03 R8 SOURCE_ONLY: native note ADD unknown + original WebView2 replay prevention PASS');
