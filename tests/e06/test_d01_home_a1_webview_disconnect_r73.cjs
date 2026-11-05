'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.resolve(__dirname,'../../coordination/express/stage_original_five_primary.py'),'utf8');
const i=source.indexOf('const a1Button=nav.querySelector('),j=source.indexOf('\n});\n})();',i);
assert.ok(i>=0&&j>i);
const handler=source.slice(i,j+4);new Function('nav','window','state','setTimeout','clearTimeout',handler);
function trial(o={}){
 let click,reply,posted,timer;
 const button={disabled:false,addEventListener(_t,fn){click=fn;}},state={textContent:''};
 const native={postMessage(v){if(o.post)throw Error('offline');posted=v;},addEventListener(_t,fn){if(o.sub)throw Error('offline');reply=fn;},removeEventListener(){if(o.unsub)throw Error('offline');}};
 const win={chrome:{get webview(){if(o.getter)throw Error('offline');return o.missing?undefined:native;}},crypto:{get getRandomValues(){if(o.crypto)throw Error('offline');return b=>{if(o.entropy)throw Error('offline');b.fill(1);return b;};}}};
 new Function('nav','window','state','setTimeout','clearTimeout',handler)({querySelector:()=>button},win,state,fn=>{timer=fn;return 1;},()=>{});
 return {state,button,native,click:()=>click({isTrusted:true}),get posted(){return posted},reply:x=>reply({isTrusted:true,source:native,data:x}),timeout:()=>timer()};
}
for(const option of [{getter:true},{missing:true},{crypto:true},{entropy:true},{sub:true},{post:true},{post:true,unsub:true}]){
 const a=trial(option);assert.doesNotThrow(a.click);assert.equal(a.button.disabled,false);assert.match(a.state.textContent,/HOLD/);
}
const ok=trial();ok.click();assert.equal(ok.posted.payload.action,'selfbuilder.a1.status');
const result={schema:'NOX-A1-NATIVE-COMMAND-STATUS-v1',state:'ACTIVE_NATIVE_BOOT_RECEIPT',native_bound:true,boot_state:'READY_FOR_EXISTING_IDLE_TICK'};
const receipt={kind:'p02NativeResult',routeId:'chat.commands',requestId:ok.posted.requestId,state:'COMPLETED',result};
ok.reply(receipt);assert.equal(ok.button.disabled,false);assert.match(ok.state.textContent,/подтверждён/);
const bad=trial();bad.click();bad.reply({...receipt,requestId:bad.posted.requestId,result:{...result,ack:false}});assert.match(bad.state.textContent,/HOLD/);
const late=trial();late.click();late.reply({...receipt,requestId:'wrong'});assert.equal(late.button.disabled,true);late.timeout();assert.match(late.state.textContent,/HOLD/);
console.log('D01_A1_WEBVIEW_DISCONNECT_SOURCE_ONLY 10/10 PASS');
