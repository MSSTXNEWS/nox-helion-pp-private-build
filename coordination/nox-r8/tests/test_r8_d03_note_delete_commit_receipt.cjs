'use strict';
// D03 source contract: compiled WPF/Windows runtime acceptance is still required.
// Run with node test_r8_d03_note_delete_commit_receipt.cjs after staging source.
const fs=require('node:fs'), path=require('node:path'), assert=require('node:assert/strict');
const cs=fs.readFileSync(path.join(__dirname,'..','overrides','src','MainWindow.xaml.cs'),'utf8');
const start=cs.indexOf('private void DeleteNote(long id, string requestId)');
const end=cs.indexOf('private void SaveFeedback(',start);
assert.ok(start>=0&&end>start,'real native WPF note delete route missing');
const m=cs.slice(start,end);
const guards=[
 'bool commitAttempted = false;',
 'CheckpointSqlite(db, "PRE_NOTE_DELETE")',
 'commitAttempted = true;',
 'tx.Commit();',
 'NOX_NOTE_DELETE_READBACK_HOLD',
 'if (commitAttempted)',
 'Send("notes.delete.receipt"',
 'SendPersonaNotes()'
];
let last=-1;
for(const guard of guards){let at=m.indexOf(guard);assert.ok(at>last,'unexpected delete commit/ACK ordering: '+guard);last=at;}
assert.ok(m.includes('Send("notes.delete.unknown", new { requestId, id, persona,'));
assert.ok(!m.includes('Send("notice", "NOX_NOTE_DELETE_COMMIT_UNKNOWN_HOLD")'));
assert.ok(m.includes('} else {\n                try { Send("notes.delete.denied"'));
assert.ok(!m.slice(m.indexOf('// Independent SQLite readback completed')).includes('Send("notes.delete.denied"'));
assert.ok(m.indexOf('if (consent != MessageBoxResult.Yes)')<m.indexOf('CheckpointSqlite(db, "PRE_NOTE_DELETE")'));
assert.ok(m.includes('id=$id AND persona=$persona')&&m.includes('AND title=$title AND content=$content AND created_at=$created'));
console.log('D03 R8 SOURCE_ONLY: pre/post-commit note deletion receipts fail-closed PASS');

// Original WebView2 dispatch executed under V8. SOURCE_ONLY, not Windows acceptance.
const html=fs.readFileSync(path.join(__dirname,'..','overrides','src','index.html'),'utf8');
assert.ok(html.includes('let noteDeleteUncertain=false;'));
const begin=html.indexOf("case 'notes':{"),finish=html.indexOf("case 'notes.add.receipt':",begin);
assert.ok(begin>=0&&finish>begin);
const nativeCases=html.slice(begin,finish);
function app(){
 const nodes={notes:{children:[],replaceChildren(){this.children=[];},append(x){this.children.push(x);}},status:{textContent:''}},sent=[];
 const $=id=>nodes[id],element=(tag,text,klass)=>({tag,textContent:text||'',className:klass||'',children:[],disabled:false,append(...xs){this.children.push(...xs);}});
 const buttons=()=>nodes.notes.children.flatMap(x=>x.children.filter(c=>c.tag==='button'));
 let seq=0;const owner=new Function('$','element','document','post','nextChatId',
  'let pendingNoteDelete=null,noteDeleteUncertain=false,visibleDraftPersona="KV";function receive(type,v){switch(type){'+nativeCases+'}}return {receive,pending:()=>pendingNoteDelete,uncertain:()=>noteDeleteUncertain};')(
  $,element,{querySelectorAll:()=>buttons()},(type,data)=>{sent.push({type,...data});return true;},()=>('req-'+(++seq)));
 return {owner,nodes,sent,buttons,click:()=>buttons()[0].onclick()};
}
const sample=[{id:17,title:'private',content:'private',timestamp:'now'}];
{
 const {owner,nodes,sent,buttons,click}=app();owner.receive('notes',{persona:'KV',rows:sample});click();const rid=sent[0].requestId;
 owner.receive('notes.delete.unknown',{requestId:'stale',id:17,reason:'NOX_NOTE_DELETE_COMMIT_UNKNOWN_HOLD'});
 assert.ok(owner.pending(),'foreign request must not release DELETE');
 owner.receive('notes.delete.unknown',{requestId:rid,id:17,persona:'KV',reason:'NOX_NOTE_DELETE_COMMIT_UNKNOWN_HOLD'});
 assert.equal(owner.pending(),null);assert.equal(owner.uncertain(),true);
 assert.match(nodes.status.textContent,/NOX_NOTE_DELETE_COMMIT_UNKNOWN_HOLD/);
 owner.receive('notes',{persona:'KV',rows:sample});assert.equal(buttons()[0].disabled,true);
 click();assert.equal(sent.filter(x=>x.type==='notes.delete').length,1,'ambiguous DELETE must not replay');
 assert.equal(sent.filter(x=>x.type==='notes.list').length,1);
}
{
 const {owner,buttons,sent,click}=app();owner.receive('notes',{persona:'KV',rows:sample});click();
 owner.receive('notes.delete.denied',{requestId:sent[0].requestId,id:17,reason:'OWNER_DECLINED'});
 assert.equal(owner.uncertain(),false);assert.equal(buttons()[0].disabled,false);
 click();assert.equal(sent.filter(x=>x.type==='notes.delete').length,2,'decline is retryable');
}
{
 const {owner,sent,click}=app();owner.receive('notes',{persona:'KV',rows:sample});click();
 owner.receive('notes.delete.receipt',{requestId:sent[0].requestId,id:17,backupVerified:true,deleted:true});
 assert.equal(owner.pending(),null);assert.equal(owner.uncertain(),false);
}
console.log('D03 R8 SOURCE_ONLY original WebView2 unknown/declined/receipt DELETE handler PASS');
