'use strict';
// D03: real original R8 WebView2 handler + original WPF owner source checks.
// SOURCE_ONLY: this does not compile C# or verify a local Windows EXE.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.join(__dirname,'..','overrides','src');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const native=fs.readFileSync(path.join(root,'MainWindow.xaml.cs'),'utf8');
assert.equal((html.match(/id="vuneoImport"/g)||[]).length,1,'one native-VUNEO control');
const start=html.indexOf("$('vuneoImport').onclick=()=>{"),end=html.indexOf("\n};",start);
assert.ok(start>0&&end>start,'original VUNEO onclick missing');
const dispatcher=html.slice(start,end+3);
const first=html.indexOf("case 'knowledge.vuneo.result':");
const last=html.indexOf("case 'knowledge.stats':",first);
assert.ok(first>0&&last>first,'correlated owner receipts missing');
const cases=html.slice(first,last);
const nodes={vuneoImport:{disabled:false},vuneoImportStatus:{textContent:''}};
const $=id=>nodes[id];
const sent=[];let offline=false,n=0;
const post=(type,data)=>{if(offline)return false;sent.push({type,...data});return true};
const nextChatId=()=>('req-owner-'+(++n));
const owner=new Function('$','post','nextChatId',
  'let pendingVuneo=null;let vuneoImportUncertain=false;'+dispatcher+
  "function receive(type,v){switch(type){"+cases+"}};"+
  "return {click:()=> $('vuneoImport').onclick(),receive,pending:()=>pendingVuneo};"
)($,post,nextChatId);
assert.equal(owner.click(),true,'user action must reach original native owner');
assert.equal(sent.length,1);
assert.equal(sent[0].type,'knowledge.vuneo');
const requestId=sent[0].requestId;
assert.equal(nodes.vuneoImport.disabled,true,'prevent duplicate owner actions');
assert.equal(owner.click(),false);assert.equal(sent.length,1,'duplicate dispatch');
owner.receive('knowledge.vuneo.result',{requestId:'stale',backupVerified:true});
assert.ok(owner.pending(),'stale native result must not settle pending');
owner.receive('knowledge.vuneo.result',{requestId,backupVerified:false});
assert.ok(owner.pending(),'unverified backup cannot be success');
owner.receive('knowledge.vuneo.denied',{requestId,reason:'OWNER_DECLINED'});
assert.equal(nodes.vuneoImport.disabled,false);
assert.equal(nodes.vuneoImportStatus.textContent,'Импорт отменён владельцем.');
assert.equal(owner.click(),true);
owner.receive('knowledge.vuneo.result',{requestId:sent[1].requestId,backupVerified:true});
assert.equal(nodes.vuneoImport.disabled,false);
assert.match(nodes.vuneoImportStatus.textContent,/резервная копия SQLite проверена/);
offline=true;
assert.equal(owner.click(),false,'broken WebView2 must fail closed');
assert.equal(nodes.vuneoImportStatus.textContent,'NOX_VUNEO_NATIVE_DISPATCH_HOLD');
assert.equal(owner.pending(),null);
const route=native.indexOf('case "knowledge.vuneo": ImportVuneoByConsent(Text("requestId"));');
const method=native.indexOf('private void ImportVuneoByConsent(string requestId)');
assert.ok(route>=0&&method>route,'original WPF owner route');
const block=native.slice(method,native.indexOf('private void ImportKnowledgeByDialog',method));
for(const expected of ['ValidWriteRequestId(requestId)','MessageBox.Show(this',
  'if (consent != MessageBoxResult.Yes)','CheckpointSqlite(db, "PRE_VUNEO_IMPORT")',
  'knowledge.ImportVuneoStaging()','knowledge.Stats()',
  'Send("knowledge.vuneo.result"','Send("knowledge.vuneo.denied"'])
  assert.ok(block.includes(expected),expected+' missing');
assert.ok(block.indexOf('CheckpointSqlite(db, "PRE_VUNEO_IMPORT")')<
  block.indexOf('knowledge.ImportVuneoStaging()'),'preimage must precede mutation');
assert.ok(block.indexOf('knowledge.ImportVuneoStaging()')<
  block.indexOf('Send("knowledge.vuneo.result"'),'success requires completed owner work');
console.log('D03 R8 SOURCE_ONLY original VUNEO owner consent/backup/receipt PASS');

/* D03 native consent replay / post-import receipt regression.
 * SOURCE_ONLY: C# compilation and owner Windows VUNEO import are NOT verified.
 */
const vuneoMethod=native.slice(
  native.indexOf('private void ImportVuneoByConsent(string requestId)'),
  native.indexOf('private void ImportKnowledgeByDialog')
);
assert.ok(native.includes('private readonly HashSet<string> consumedVuneoRequestIds = new(StringComparer.Ordinal);'));
assert.ok(!native.includes('consumedVuneoRequestOrder'), 'never evict consumed owner requests');
const replayAt=vuneoMethod.indexOf('!consumedVuneoRequestIds.Add(requestId)');
const consentAt=vuneoMethod.indexOf('MessageBox.Show(this');
assert.ok(replayAt>0&&replayAt<consentAt,'reject duplicate requestId before owner modal');
assert.ok(vuneoMethod.includes('NOX_VUNEO_REPLAY_HOLD'),'explicit replay denial');
const capAt=vuneoMethod.indexOf('consumedVuneoRequestIds.Count >= 512');
assert.ok(capAt>0&&capAt<replayAt&&replayAt<consentAt,
  'exhausted nonce budget must reject new work before consent');
assert.ok(vuneoMethod.includes('!consumedVuneoRequestIds.Contains(requestId)'),
  'old request IDs must still be recognized after the budget is exhausted');
assert.ok(vuneoMethod.includes('NOX_VUNEO_REQUEST_LIMIT_HOLD'),
  'exhaustion must have an explicit fail-closed native receipt');
assert.ok(!vuneoMethod.includes('consumedVuneoRequestIds.Remove('),
  'eviction reopens previously consumed owner consent');
const preimageAt=vuneoMethod.indexOf('CheckpointSqlite(db, "PRE_VUNEO_IMPORT")');
const importAt=vuneoMethod.indexOf('knowledge.ImportVuneoStaging()');
const committedAt=vuneoMethod.indexOf('importCompleted = true;');
const ackAt=vuneoMethod.indexOf('Send("knowledge.vuneo.result"');
const refreshAt=vuneoMethod.indexOf('knowledge.Stats()');
assert.ok(consentAt<preimageAt&&preimageAt<importAt&&importAt<committedAt&&committedAt<ackAt&&ackAt<refreshAt,
  'native owner consent -> verified preimage -> import -> correlated receipt -> optional stats');
assert.ok(vuneoMethod.includes('if (!importCompleted)') &&
          vuneoMethod.indexOf('if (!importCompleted)')>refreshAt,
  'post-import notification faults must not emit false import-denied');


// D03 R8: an importer exception after entering KnowledgeStore does NOT prove a
// rollback. The renderer must keep unknown state distinct from owner refusal,
// hold an uncertain import instead of inviting a potentially duplicating retry,
// and accept only the matching native requestId with verified backup.
assert.ok(vuneoMethod.includes('bool importAttempted = false;'));
assert.ok(vuneoMethod.indexOf('CheckpointSqlite(db, "PRE_VUNEO_IMPORT")') <
          vuneoMethod.indexOf('importAttempted = true;'));
assert.ok(vuneoMethod.indexOf('importAttempted = true;') <
          vuneoMethod.indexOf('knowledge.ImportVuneoStaging()'));
assert.ok(vuneoMethod.includes('if (importAttempted)') &&
          vuneoMethod.includes('Send("knowledge.vuneo.unknown"'));
assert.ok(vuneoMethod.includes('NOX_VUNEO_COMMIT_UNKNOWN_HOLD'));
assert.ok(vuneoMethod.includes('else\n                        Send("knowledge.vuneo.denied"'));
const unknownScript=html.slice(html.indexOf("case 'knowledge.vuneo.unknown':"),html.indexOf("case 'knowledge.vuneo.denied':"));
assert.ok(unknownScript.includes('vuneoImportUncertain=true'));
assert.ok(unknownScript.includes("v?.requestId!==pendingVuneo.requestId"));
offline=false;
assert.equal(owner.click(),true,'owner action after failed WebView2 transport');
const uncertainId=sent.at(-1).requestId;
owner.receive('knowledge.vuneo.unknown',{requestId:'stale',reason:'NOX_VUNEO_COMMIT_UNKNOWN_HOLD',backupVerified:true});
assert.ok(owner.pending(),'foreign/late receipt cannot settle owner import');
owner.receive('knowledge.vuneo.unknown',{requestId:uncertainId,reason:'NOX_VUNEO_COMMIT_UNKNOWN_HOLD',backupVerified:false});
assert.ok(owner.pending(),'unverified backup may not admit unknown receipt');
owner.receive('knowledge.vuneo.unknown',{requestId:uncertainId,reason:'NOX_VUNEO_COMMIT_UNKNOWN_HOLD',backupVerified:true});
assert.equal(owner.pending(),null);
assert.equal(nodes.vuneoImport.disabled,true,'unknown SQLite outcome prevents an immediate replay');
assert.match(nodes.vuneoImportStatus.textContent,/NOX_VUNEO_COMMIT_UNKNOWN_HOLD/);
assert.equal(owner.click(),false,'programmatic handler cannot bypass disabled button');
console.log('D03 R8 SOURCE_ONLY: unknown partial import fail-closed / requestId / verified SQLite preimage PASS');
