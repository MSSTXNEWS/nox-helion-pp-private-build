// D03 R5: original INSTALL never overwrites a synchronous owner HOLD.
// SOURCE_ONLY, not Windows owner consent, file readback or process exit.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../../coordination/express/stage_original_five_primary.py',import.meta.url),'utf8');
const start=source.indexOf('   // D03 R5: do not overwrite a synchronous native owner rejection');
const end=source.indexOf('\n }\n // SETTINGS',start);
assert.ok(start>0&&end>start,'original INSTALL handoff anchors');
const owner=source.slice(start,end);
test('D03 synchronous native owner refusal survives and throwing click holds',()=>{
 assert.equal(source.split("if(name==='INSTALL'){").length-1,1);
 assert.ok(owner.indexOf("state.textContent='INSTALL: передача")<owner.indexOf('try{invokeMatches[0].click();}'));
 const run=(name,click)=>{
   const state={textContent:''};
   const dispatch=vm.runInNewContext('(function(name,invokeMatches,state){'+owner+'})',{}, {timeout:1000});
   dispatch(name,[{click:()=>click(state)}],state);
   return state.textContent;
 };
 assert.equal(run('INSTALL',s=>{s.textContent='NATIVE_NO_CONSENT_HOLD';}),'NATIVE_NO_CONSENT_HOLD');
 assert.match(run('INSTALL',()=>{throw Error('disposed owner');}),/HOLD$/);
 assert.match(run('INSTALL',()=>{}),/результат не подтверждён/);
 assert.match(run('MODELS',()=>{}),/результат ожидается/);
});
