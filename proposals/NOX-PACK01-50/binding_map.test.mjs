import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
const root=new URL('./',import.meta.url);
const map=JSON.parse(readFileSync(new URL('owner-binding-map.json',root),'utf8'));
const catalog=JSON.parse(readFileSync(new URL('catalog.json',root),'utf8'));
test('one binding proof for exactly fifty canonical route IDs',()=>{
  assert.equal(map.routes.length,50);
  assert.deepEqual(new Set(map.routes.map(x=>x.routeId)),new Set(catalog.actions.map(x=>x.routeId)));
  assert.equal(new Set(map.routes.map(x=>x.taskId)).size,50);
});
test('32 original owner method bindings and 18 distinct HOLD routes',()=>{
  const bound=map.routes.filter(x=>x.sourceBinding);
  const hold=map.routes.filter(x=>!x.sourceBinding);
  assert.equal(bound.length,32);
  assert.equal(hold.length,18);
  assert.equal(map.counts.exeIntegrated,0);
  assert.equal(map.counts.releaseAccepted,0);
  assert.equal(map.counts.p02+map.counts.p03+map.counts.p04+map.counts.e05,32);
  assert.deepEqual(new Set(hold.map(x=>x.routeId)),
                   new Set(map.remainingNativeBlockers.map(x=>x.routeId)));
});
test('no source-bound method claims installed acceptance',()=>{
  for(const item of map.routes){
    assert.equal(item.exeIntegrated,false);
    assert.equal(item.releaseAccepted,false);
    assert.equal(item.hardwareAccepted,false);
    assert.ok(typeof item.blocker==='string' && item.blocker.length>0);
    if(item.sourceBinding){
      const source=item.sourceBinding.split(':')[0];
      assert.ok(source.startsWith('proposals/NOX-PACK01-50/'));
      const local=source.substring('proposals/NOX-PACK01-50/'.length);
      assert.ok(existsSync(new URL(local,root)),local);
    }else{
      assert.equal(item.componentCI,'NOT_RUN');
    }
  }
});
test('all four owner families are traceable to exact focused Windows CI receipts',()=>{
  assert.ok(map.proof.p02Owner.runId);
  assert.ok(map.proof.p03Owner.runId);
  assert.ok(map.proof.e05Owner.runId);
  assert.ok(map.proof.p04Owner.runId);
  assert.equal(map.proof.finalExe.status,'NOT_INTEGRATED');
});
