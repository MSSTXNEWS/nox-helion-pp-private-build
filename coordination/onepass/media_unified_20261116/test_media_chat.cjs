'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const {webcrypto} = require('node:crypto');
const code = fs.readFileSync(require('node:path').join(__dirname,'nox-media-chat.js'), 'utf8');
const ID='a'.repeat(32);
class Element {
  constructor(tag) { this.tag=tag;this.children=[];this.attrs={};this.listeners={};this.dataset={};this.textContent='';this.value='';this.parentNode=null; }
  append(...children) { for(const node of children){this.children.push(node);node.parentNode=this;} }
  appendChild(node) {this.append(node);return node;}
  insertBefore(node,before){const i=this.children.indexOf(before);if(i<0)throw Error('missing before');this.children.splice(i,0,node);node.parentNode=this;}
  setAttribute(n,v){this.attrs[n]=v;}
  addEventListener(n,cb){(this.listeners[n]??=[]).push(cb);}
  click(){return this.listeners.click?.[0]?.();}
  removeEventListener(n,cb){this.listeners[n]=(this.listeners[n]||[]).filter(x=>x!==cb);}
  focus(){this.focused=true;}
  scrollIntoView(){}
  remove(){if(this.parentNode)this.parentNode.children=this.parentNode.children.filter(x=>x!==this);}
}
function fixture(available=true, lostReceipt=false, saved=new Map()){
  const form=new Element('form'),input=new Element('textarea'),stream=new Element('section'),parent=new Element('div');
  form.id='chatForm';input.id='prompt';stream.id='messages';parent.append(stream,form);
  const calls=[];let jobRequests=0;
  const document={readyState:'complete',visibilityState:'visible',createElement:tag=>new Element(tag),getElementById:id=>({chatForm:form,prompt:input,messages:stream})[id]||null};
  const response=obj=>({ok:true,status:200,json:async()=>obj});
  const fetch=async(url,init={})=>{
    calls.push({url,init});
    if(url==='/api/ui/media')return response(available?{image:true,video:true,idempotency_v1:true}:{image:false,video:false,reason:'HOLD_MEDIA_NOT_INSTALLED'});
    if(url==='/api/ui/media/jobs'&&init.method==='POST'){
      jobRequests++;
      if(lostReceipt)throw Error('connection lost after submit');
      return response({id:ID,kind:JSON.parse(init.body).kind,state:'QUEUED'});
    }
    if(url.startsWith('/api/ui/media/requests/'))return response({id:ID,kind:'image'});
    if(url==='/api/ui/media/jobs/'+ID)return response({id:ID,kind:jobRequests===2?'video':'image',state:'COMPLETED',generation_verified:true,outputs:[{url:'/api/ui/media/jobs/'+ID+'/outputs/0'}]});
    throw Error('unexpected fetch '+url);
  };
  const sessionStorage={getItem:k=>saved.get(k),setItem:(k,v)=>saved.set(k,v),removeItem:k=>saved.delete(k)};
  const context={window:{},document,location:{href:'http://localhost/nox-web-v29/pc/resonance.html',origin:'http://localhost'},URL,setTimeout,clearTimeout,AbortController,crypto:webcrypto,sessionStorage,fetch,console};
  vm.runInNewContext(code,context,{timeout:3000});
  return {form,input,stream,parent,calls};
}
function find(node,pred){if(pred(node))return node;for(const child of node.children){const r=find(child,pred);if(r)return r;}return null;}
const submit=async(form)=>{
 const event={preventDefault(){this.prevented=true;},stopImmediatePropagation(){this.stopped=true;}};
 const handler=form.listeners.submit?.[0];assert(handler);
 await handler(event);return event;
};
test('one existing authenticated media API is called and real output embedded in chat',async()=>{
 const f=fixture();const bar=find(f.parent,x=>x.id==='noxMediaToolbar');assert(bar);
 const button=find(bar,x=>x.dataset.kind==='image');button.listeners.click[0]();
 f.input.value='осенний лес'; const event=await submit(f.form);
 assert.equal(event.prevented,true);assert.equal(event.stopped,true);
 assert.equal(f.input.value,'');
 assert.equal(f.calls.filter(x=>x.url==='/api/ui/media/jobs').length,1);
 const image=find(f.stream,x=>x.tag==='img');assert(image);assert.equal(image.src,'/api/ui/media/jobs/'+ID+'/outputs/0');
});
test('a lost POST response survives a reload and reconnects without posting a second job',async()=>{
 const saved=new Map();const f=fixture(true,true,saved);
 f.input.value='/image приватное описание';await submit(f.form);
 const posted=JSON.parse(f.calls.find(x=>x.url==='/api/ui/media/jobs').init.body);
 assert.match(posted.client_request_id,/^[a-f0-9]{32}$/);
 assert.equal([...saved.values()][0].includes(posted.prompt),false);
 const reloaded=fixture(true,false,saved);
 await new Promise(resolve=>setImmediate(resolve));
 assert(reloaded.calls.some(x=>x.url==='/api/ui/media/requests/'+posted.client_request_id));
 assert.equal(reloaded.calls.some(x=>x.init.method==='POST'),false);
 assert(find(reloaded.stream,x=>x.tag==='img'));
 assert.equal(saved.size,0);
});
test('without backend weights no success is fabricated and old chat stays available',async()=>{
 const f=fixture(false);
 f.input.value='/video ночное небо';const event=await submit(f.form);
 assert.equal(event.prevented,true);assert.equal(f.calls.some(x=>x.url==='/api/ui/media/jobs'),false);
 assert.equal(find(f.stream,x=>x.tag==='img'),null);
 assert.equal(find(f.stream,x=>x.tag==='video'),null);
 assert(find(f.stream,x=>x.tag==='p'&&x.textContent.includes('HOLD')));
 f.input.value='обычный вопрос';const e=await submit(f.form);assert.equal(e.prevented,undefined);
});
