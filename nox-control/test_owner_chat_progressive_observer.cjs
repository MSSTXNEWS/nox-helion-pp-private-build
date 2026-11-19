/* Execute the actual QA observer with split DOM spans and real Web Streams.
 * This is a measurement regression fixture, not native/browser acceptance. */
'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'owner_chat_browser_qa.py'),'utf8');
const observer=source.match(/OBSERVER_JS = r"""([\s\S]*?)"""/)[1]
  .replace('__CONFIG__',JSON.stringify({did:'a'.repeat(32)}));
const snapshot=source.match(/SNAPSHOT_JS = r"""([\s\S]*?)"""/)[1];
const encoder=new TextEncoder();

function fixture(){
  let clock=0,upstream,raf=[],observers=[];
  const style={display:'block',visibility:'visible',opacity:'1',contentVisibility:'visible',
    overflowX:'visible',overflowY:'visible'};
  class Element{
    constructor(parent=null,text=''){this.parentElement=parent;this.text=text;this.children=[];this.style={...style};}
    get innerText(){return this.text+this.children.map(n=>n.innerText).join('');}
    get textContent(){return this.innerText;}
    getBoundingClientRect(){return {left:20,right:300,top:20,bottom:45,x:20,y:20,width:280,height:25};}
    contains(node){return node===this||this.children.some(child=>child.contains(node));}
    querySelectorAll(selector){return selector==='.tok'?this.children.filter(node=>node.token):[];}
  }
  const mount=new Element(),article=new Element(mount),body=new Element(article);
  mount.children=[article];article.children=[body];
  let pending=[body];
  const document={hidden:false,getElementById:id=>id==='messages'?mount:null,
    querySelectorAll:selector=>selector==='#messages .v24-msg.nox.streaming .body'?pending:[],
    querySelector:()=>null};
  class Canvas{getContext(){return null;}}
  class Observer{constructor(callback){this.callback=callback;}observe(target){observers.push({target,callback:this.callback});}}
  const native=new Response(new ReadableStream({start(controller){upstream=controller;}}));
  const window={fetch:async()=>native,NOX_NATIVE_OWNER:true};
  const context={window,document,HTMLCanvasElement:Canvas,MutationObserver:Observer,
    TextEncoder,TextDecoder,Request,Response,URL,Intl,ReadableStream,
    location:{origin:'https://nox.local',href:'https://nox.local/nox-web-v29/pc/resonance.html'},
    innerWidth:1000,innerHeight:800,performance:{now:()=>clock},
    getComputedStyle:node=>node.style,requestAnimationFrame:callback=>raf.push(callback),
    addEventListener:(event,callback)=>{if(event==='DOMContentLoaded')callback();}};
  vm.createContext(context);vm.runInContext(observer,context);
  const drain=()=>new Promise(resolve=>setImmediate(resolve));
  async function flush(){await drain();const tasks=raf;raf=[];tasks.forEach(fn=>fn(clock));await drain();}
  function mutate(){observers.filter(x=>x.target===mount).forEach(x=>x.callback([]));}
  function write(text,split){
    body.text='';body.children=split?Array.from(text,c=>{const n=new Element(body,c);n.token=true;return n;}):[];
    if(!split)body.text=text;
    mutate();
  }
  return {window,mount,article,body,Element,document,flush,write,mutate,
    get q(){return window.__NOX_BROWSER_QA;},
    capture:async()=>{await window.fetch('/api/nox/chat/stream',{method:'POST'});await flush();},
    emit:async frame=>{clock+=20;upstream.enqueue(encoder.encode(JSON.stringify(frame)+'\n'));await flush();},
    close:async()=>{upstream.close();await flush();},
    view:()=>vm.runInContext('('+snapshot+')()',context),
    pending:values=>{pending=values;}};
}
async function start(f){
  await f.capture();
  await f.emit({type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM'});
  await f.emit({type:'start'});
}
async function done(f){
  await f.emit({type:'done',saved:true,s03_integrated:true,dialog_id:'a'.repeat(32)});
  await f.close();
}

test('one-character token spans yield growing cumulative visible prefixes before done',async()=>{
  const f=fixture();await start(f);let text='';
  for(const token of '1,2,3'){
    await f.emit({type:'delta',text:token});text+=token;f.write(text,true);await f.flush();
  }
  assert(f.body.children.every(node=>node.textContent.length===1));
  assert(f.body.children.every(node=>node.textContent.length<3),'old per-node predicate misses every token');
  assert.deepEqual(Array.from(f.q.uiPrefixLengthsBeforeDone),[3,4,5]);
  assert.equal(f.q.uiBeforeDone,true);assert.equal(f.q.nativeDone,null);
  await done(f);const value=f.view();
  assert.equal(value.dom_answer_matches_native,true);
  assert(value.ui_first_ms<value.native_done_ms);assert.equal(value.ui_token_span_peak,5);
});

test('whole-body replacement also measures real growing prefixes',async()=>{
  const f=fixture();await start(f);let text='';
  for(const token of ['1,2',',3',',4']){
    await f.emit({type:'delta',text:token});text+=token;f.write(text,false);await f.flush();
  }
  assert.deepEqual(Array.from(f.q.uiPrefixLengthsBeforeDone),[3,5,7]);
  assert.equal(f.view().dom_answer_matches_native,true);await done(f);
});

test('a clone observer lag is retried after the actual native delta without a second DOM mutation',async()=>{
  const f=fixture();await start(f);
  f.write('1,2',true);await f.flush();assert.equal(f.q.uiFirst,null);
  await f.emit({type:'delta',text:'1,2'});
  assert.deepEqual(Array.from(f.q.uiPrefixLengthsBeforeDone),[3]);await done(f);
});

test('invisible ancestors and invisible token children do not establish visible progress',async()=>{
  const f=fixture();await start(f);
  f.article.style.opacity='0';await f.emit({type:'delta',text:'1,2'});f.write('1,2',true);await f.flush();
  assert.equal(f.q.uiFirst,null);f.article.style.opacity='1';
  f.body.children[0].style.opacity='0';f.mutate();await f.flush();assert.equal(f.q.uiFirst,null);
  f.body.children[0].style.opacity='1';f.mutate();await f.flush();assert.equal(f.q.uiBeforeDone,true);
  await done(f);
});

test('a previous assistant body cannot replace the exact captured streaming body',async()=>{
  const f=fixture(),other=new f.Element(f.mount,'1,2,3');f.mount.children.unshift(other);
  await start(f);await f.emit({type:'delta',text:'1,2,3'});f.mutate();await f.flush();
  assert.equal(f.q.uiFirst,null);assert.equal(f.view().dom_answer_matches_native,false);await done(f);
});

test('a whole answer first inserted after native done still fails progressive observation',async()=>{
  const f=fixture();await start(f);await f.emit({type:'delta',text:'1,2'});
  await f.emit({type:'delta',text:',3'});await done(f);
  f.write('1,2,3',false);await f.flush();
  assert.equal(f.q.uiBeforeDone,false);assert.deepEqual(Array.from(f.q.uiPrefixLengthsBeforeDone),[]);
  assert.deepEqual(Array.from(f.q.uiLengths),[5]);assert.equal(f.view().dom_answer_matches_native,true);
});

test('ambiguous multiple streaming bodies fail closed',async()=>{
  const f=fixture(),other=new f.Element(f.mount,'1,2,3');f.mount.children.push(other);f.pending([f.body,other]);
  await start(f);await f.emit({type:'delta',text:'1,2,3'});f.write('1,2,3',true);await f.flush();
  assert.equal(f.q.uiBody,null);assert.equal(f.q.uiFirst,null);await done(f);
});
