/** W08 R96 · executes original MEGA814 bootstrap, source-level only; never E07. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('./mega814.mjs',import.meta.url),'utf8');
const start=source.indexOf('export function bootstrapMega814('),end=source.indexOf('\nPromise.all(',start);
assert.ok(start>=0&&end>start,'ORIGINAL_BOOTSTRAP_REQUIRED');
const unit=source.slice(start,end).replace('export function','function')+'\nbootstrapMega814';
function check({origin='https://nox.local',pathname='/',search='',hash='',host=true,crypto=true,reduce=false,eco=false}={}){
 const webview=host?{postMessage(){},addEventListener(){},removeEventListener(){}}:null;
 const crypt=crypto?{getRandomValues(){}}:null;
 let created=0,disposed=0,menuArgs;
 const client={request(){},destroy(){disposed++}};
 const doc={getElementById:id=>['menu','control'].includes(id)?{}:null,
  body:{classList:{contains(){return false}}},documentElement:{dataset:{}}};
 const win={location:{origin,pathname,search,hash},chrome:{webview},crypto:crypt,addEventListener(){},
  matchMedia:q=>({matches:q.includes('prefers-reduced-motion')?reduce:eco,addEventListener(){},removeEventListener(){}})};
 const ctx={document:doc,window:win,validateMega:()=>({}),validateMenuV2:()=>({}),
  createNativeReadOnlyPort:()=>({available:host,close(){}}),
  createE05ReadOnlyStore:()=>({hostReady:false,close(){}}),
  menuWorlds:(...a)=>{menuArgs=a;return{destroy(){}}},workViews:()=>({destroy(){}}),
  cast:()=>({remove(){}}),space:()=>({destroy(){}}),
  createNativeMenuClient:({webview:actual,cryptoRef})=>{
   created++;assert.equal(actual,webview);assert.equal(cryptoRef,crypt);
   if(!cryptoRef)throw Error('NOX_NATIVE_HOST_REQUIRED');return client;
  }};
 const bootstrap=vm.runInNewContext(unit,ctx,{timeout:1000});
 const app=bootstrap({},{});assert.equal(app.e07,'HOLD');app.destroy();
 return {created,disposed,bound:menuArgs[4]===client,motion:doc.documentElement.dataset.mega814Motion};
}
const yes=check();assert.equal(yes.created,1);assert.equal(yes.disposed,1);assert.equal(yes.bound,true);
for(const bad of [{origin:'https://bad.invalid'},{pathname:'/about'},{search:'?x=1'},
 {hash:'#x'},{host:false}]){
 const no=check(bad);assert.equal(no.created,0);assert.equal(no.disposed,0);assert.equal(no.bound,false);
}
const noCrypto=check({crypto:false});assert.equal(noCrypto.bound,false);assert.equal(noCrypto.disposed,0);
assert.equal(check({reduce:true}).motion,'REDUCED');assert.equal(check({eco:true}).motion,'ECO');
console.log('MEGA814_ORIGINAL_NATIVE_BINDING_PASS 9/9 SOURCE_ONLY E07_HOLD');
