/* NOX V26 fail-closed source contract checks.
 * Runs after exact SHA256 baseline restoration and V26 patch, before build.
 * Static checks are not evidence of live OneHost or physical GPU acceptance.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import crypto from 'node:crypto';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../dist');
const file=p=>fs.readFileSync(path.join(root,p),'utf8');
const digest=p=>crypto.createHash('sha256').update(fs.readFileSync(path.join(root,p))).digest('hex');
const expected={
  'chat.html':'f8c9d1f89371ec3dbf257e140910e86effd6560a71c5f69231915a3e7d0a2b77',
  'nox-chat.js':'0734c06fb3867307b3381bcac3a41703878f935117516de893be63e0be46ce49',
  'nox-telemetry.js':'459a2eec7bc3b3a56120a2038b5197b2d5d83f608ab450228fffc69ddb3b3627',
  'nox-function-catalog.js':'175c1d8be3d9bd6c5011faade2a29cf6f253bc2e1d9769898b267ca969e84816',
  'nox-universe-v19.js':'4c2c9a2d456da77bfeab74f2aa5037b8828eb723a3690579c382b93fe2af6d68'
};
test('exact V26 changes applied to only five pre-locked source files',()=>{
  for(const [p,sha] of Object.entries(expected))assert.equal(digest(p),sha,p+' postimage drift');
});
test('original D02 and 14 PBR physical worlds preserve byte-identical originals',()=>{
  assert.equal(digest('nox-home.mjs'),'8066bc0a0f8ef5bb5f0fb1f58ad3f6ee29dc8506385c09d77d38d4235c7e42e9');
  assert.equal(digest('nox-engines/physical-worlds-v7.mjs'),'3f27609ea37b96579a711928e4c67778ec71e2ff7b090a3b7bb41e29040f3905');
});
test('all existing original ten pages remain in the candidate',()=>{
  for(const p of ['index','chat','cinema','install','memory','models','projects','settings','system','training'])
    assert.ok(fs.existsSync(path.join(root,p+'.html')),'Missing '+p+'.html');
});
test('real native Resonance microphone and translation targets exist',()=>{
  const html=file('chat.html'),catalog=file('nox-function-catalog.js');
  for(const id of ['chatDictate','chatTranslate','chatForm']) assert.ok(html.includes('id="'+id+'"'),id+' missing in Resonance');
  assert.match(catalog,/'voice','Голос NOX','mic','chat','chatDictate'/);
  assert.match(catalog,/'translation','Перевод RU ↔ ES','languages','chat','chatTranslate'/);
  assert.doesNotMatch(catalog,/'voice','Голос NOX','mic','settings','native-push-panel'/);
});
test('all 5 public modules use the existing shared V19 runtime without fake actions',()=>{
  const cat=file('nox-function-catalog.js'),shared=file('nox-universe-v19.js');
  for(const m of ['Календарь','Уведомления','Новости','Погода','Валюта']){
    assert.ok(cat.includes("'v19:"+m+"'"),m+' catalog binding absent');
    assert.ok(shared.includes("'"+m+"'"),m+' original module absent');
  }
  assert.ok(cat.includes('window.NOX_UNIVERSE_V19.open(module)'));
  assert.ok(shared.includes("function open(moduleName)"));
  assert.ok(cat.includes("!native"),'native UI must preserve existing owner routes');
});
test('real training controls only invoke attested local POST endpoints',()=>{
  const s=file('nox-telemetry.js');
  for(const command of ['compare','evaluate','rollback'])assert.ok(s.includes("'"+command+"'"),'Missing training action '+command);
  assert.ok(s.includes("capability.endpoint==='/api/nox/training/'+ui"));
  assert.ok(s.includes("capability.method==='POST'"));
  assert.ok(s.includes("cap.endpoint!=='/api/nox/training/'+action"));
  assert.ok(s.includes('window.confirm('),'Rollback must require owner confirmation');
  assert.ok(s.includes('expected_sha256'),'Rollback needs exact expected checkpoint hash');
  assert.ok(s.includes("не PASS обучения"),'No fake training SUCCESS');
});
test('native chat STOP, S03 uncertainty, and frame limits must remain fail closed',()=>{
  const s=file('nox-chat.js');
  for(const term of ['nativeReplayHold=true','run.controller.abort();','submitted=true','/api/nox/stop',
    'result.length+frame.text.length>2000000','line.length>262144'])
    assert.ok(s.includes(term),'Missing native chat protection '+term);
  assert.ok(s.includes("Обновите историю S03 перед повторной отправкой"));
});
console.log('NOX_WEB_V26_SOURCE_CONTRACT_TESTS_DEFINED');
