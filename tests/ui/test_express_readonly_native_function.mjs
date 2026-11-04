import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import {nativeOwnerReceiptHolds} from '../../ui/onehost-menu-bindings.mjs';

// Extract the actual installed-source handler instead of reimplementing it.
const source=readFileSync(new URL('../../ui/menu-pages/menu.js',import.meta.url),'utf8');
const fragment=source.slice(source.indexOf('async function nativeRequest('),
                            source.indexOf('function liveChat('));
assert.ok(fragment.startsWith('async function nativeRequest('));

async function probe(receipt,{late=false,reject=false}={}){
 let resolve,deny,output;
 const statuses=[],fallback=[],calls=[];
 const pendingReply=new Promise((ok,no)=>{resolve=ok;deny=no});
 const el=()=>({isConnected:true,textContent:'',append(){}});
 const native=new Function('el','button','client','setDetails','world','pending',
    'say','nativeOwnerReceiptHolds',fragment+'\nreturn nativeRequest;')(
    el,()=>({}),{request:(route)=>{calls.push(route);return pendingReply;}},
    (...args)=>{output=args.at(-1)},()=>{},id=>fallback.push(id),
    x=>statuses.push(x),nativeOwnerReceiptHolds);
 const running=native('models.catalog',{}, {id:'model-library',name:'Модели',world:'pc'});
 if(late)output.isConnected=false;
 if(reject)deny(Error('HOST_DENIED'));else resolve(receipt);
 await running;
 return {statuses,fallback,calls,output:output.textContent};
}

test('read-only function requires exact real native result, not merely COMPLETED',async()=>{
 const good=await probe({routeId:'models.catalog',state:'COMPLETED',result:{models:[]}});
 assert.deepEqual(good.calls,['models.catalog']);
 assert.match(good.output,/"models": \[\]/);
 assert.deepEqual(good.fallback,[]);
 for(const bad of [
  {routeId:'models.catalog',state:'COMPLETED',errorCode:'PROVIDER_OFFLINE_HOLD',result:{models:[]}},
  {routeId:'models.catalog',state:'COMPLETED',ack:false,result:{models:[]}},
  {routeId:'models.catalog',state:'COMPLETED',result:{status:'CONSENT_REQUIRED',models:[]}},
  {routeId:'chat.history',state:'COMPLETED',result:{models:[]}},
  {routeId:'models.catalog',state:'COMPLETED'}
 ]) {
  const got=await probe(bad);
  assert.deepEqual(got.fallback,['model-library']);
  assert.equal(got.statuses.some(s=>s.startsWith('Получены данные')),false);
 }
});

test('late success and failure cannot mutate another opened screen',async()=>{
 for(const options of [{late:true},{late:true,reject:true}]) {
  const got=await probe({routeId:'models.catalog',state:'COMPLETED',result:{models:[]}},options);
  assert.deepEqual(got.statuses,[]);
  assert.deepEqual(got.fallback,[]);
 }
});
