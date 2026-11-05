import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {markP01RoutePending,invokeP01NativeRouteFeedback} from './mount-p01.mjs';

test('M07 retry clears stale successful native ACK before a fresh request',()=>{
  const dataset={noxNativeAck:'true',noxNativeReceipt:'old-receipt',
    noxNativeState:'confirmed',noxNativeReason:'OLD_REASON',noxRoute:'models.catalog'};
  markP01RoutePending(dataset);
  assert.equal(dataset.noxNativeState,'pending');
  for(const key of ['noxNativeAck','noxNativeReceipt','noxNativeReason'])
    assert.equal(Object.hasOwn(dataset,key),false,key);
  assert.equal(dataset.noxRoute,'models.catalog');
  markP01RoutePending(dataset);
  assert.equal(dataset.noxNativeState,'pending');
});

test('M07 native menu click resets old receipt before awaiting native dispatcher',()=>{
  const src=readFileSync(new URL('./mount-p01.mjs',import.meta.url),'utf8');
  const guarded=src.indexOf('if(disposed||dispatcher.isPending(item.routeId))return;');
  const pending=src.indexOf('markP01RoutePending(item.element.dataset);',guarded);
  const dispatched=src.indexOf('const result=await invokeP01NativeRouteFeedback(dispatcher,item.routeId);',pending);
  assert.ok(guarded>=0&&pending>guarded&&dispatched>pending,
    'a fresh route must clear previous ACK before invoking native host');
  assert.ok(src.includes('return nativeP01Feedback(await dispatcher.invoke(routeId));'));
  assert.ok(src.includes('isP01PrimaryRouteTarget(item,event?.target,routeEntries)'));
  assert.ok(src.includes("target.matches?.('a[href]')"));
});

// A rejected native pipe must remain HOLD, not a fictitious confirmation.
test('M07 native route helper preserves positive owner receipts and IPC failure HOLD',async()=>{
  const ok=await invokeP01NativeRouteFeedback({invoke:async route=>{
    assert.equal(route,'models.catalog');
    return {ok:true,receiptId:'owner-verified-1'};
  }},'models.catalog');
  assert.deepEqual(ok,{state:'confirmed',receiptId:'owner-verified-1'});
  const rejected=await invokeP01NativeRouteFeedback({invoke:async()=>{
    throw new Error('sensitive native error');
  }},'models.catalog');
  assert.deepEqual(rejected,{state:'hold',reason:'NATIVE_DISPATCH_FAILED'});
});
