// Node 22: node --test tests/test_canonical_panel.mjs
// SOURCE-level regression only: this does not certify installed Windows E07.
import test from 'node:test';
import assert from 'node:assert/strict';
import { mountOpportunityPanel } from '../engine/nox_canonical_panel.mjs';

class FakeElement {
  constructor(tag = 'div') { this.tag=tag;this.dataset={};this.hidden=false;this.childNodes=[];this.listeners=new Map();this.attributes={};this.value='';this.focused=false;this.textContent=''; }
  append(...nodes){this.childNodes.push(...nodes)}
  replaceChildren(...nodes){this.childNodes=nodes}
  attachShadow(){this.shadowRoot=new FakeElement('shadowRoot');return this.shadowRoot}
  setAttribute(k,v){this.attributes[k]=String(v)}
  addEventListener(type,callback){const a=this.listeners.get(type)||[];a.push(callback);this.listeners.set(type,a)}
  async fire(type,event={}){for(const callback of this.listeners.get(type)||[])await callback(event)}
  focus(){this.focused=true}
  set innerHTML(html){
    this.html=html;this.refs=new Map();
    for(const key of ['input','.grid','[role=status]','[data-action=more]','.detail','[data-theme]'])this.refs.set(key,new FakeElement(key));
  }
  querySelector(selector){return this.refs.get(selector)}
}
const button=(dataset)=>({target:{closest:()=>({dataset})}});
const tick=async()=>{for(let i=0;i<5;i++)await Promise.resolve()};

test('canonical OIE mounts only inside owner host; actions and lifecycle work',async()=>{
  const original={document:globalThis.document,HTMLElement:globalThis.HTMLElement,fetch:globalThis.fetch};
  globalThis.HTMLElement=FakeElement;
  globalThis.document={createElement:(tag)=>new FakeElement(tag)};
  let fetchCount=0,backCount=0,jobCount=0,dispatched=0;
  globalThis.fetch=async url=>{
    fetchCount++;
    return {ok:true,json:async()=>({ok:true,result:url.startsWith('/api/inspect')
      ?{idea:{id:'idea-1',name:'Idea 1'}}
      :{ideas:Array.from({length:21},(_,i)=>({id:'idea-'+i,name:'Idea '+i,status:'IDEA_UNVERIFIED'}))}})};
  };
  try{
    const host=new FakeElement('section');
    assert.throws(()=>mountOpportunityPanel(host),/NOX_ROUTE_NOT_APPROVED/);
    host.dataset.noxScreen='opportunity-engine';
    const instance=mountOpportunityPanel(host,{apiBase:'',onBack:()=>{backCount++},onEvent:()=>{dispatched++},requestJob:async(action,params)=>{jobCount++;assert.equal(params.count,3);return {ok:true,result:{action}}}});
    await tick();
    const root=host.shadowRoot,panel=root.childNodes[1],grid=panel.querySelector('.grid');
    assert.equal(grid.childNodes.length,9);
    assert.equal(panel.querySelector('[data-action=more]').hidden,false);
    await panel.fire('click',button({action:'more'}));
    assert.equal(grid.childNodes.length,18);
    const input=panel.querySelector('input');
    input.value='Idea 1';await input.fire('input');
    assert.equal(grid.childNodes.length,9);
    await panel.fire('click',button({ideaId:'idea-1'}));
    assert.equal(panel.querySelector('.detail').attributes.tabindex,'-1');
    assert.equal(panel.querySelector('.detail').focused,true);
    await root.fire('keydown',{key:'Escape'});
    assert.equal(panel.querySelector('.detail').hidden,true);
    await root.fire('keydown',{key:'k',ctrlKey:true,preventDefault(){}});
    assert.equal(input.focused,true);
    await panel.fire('click',button({action:'generate'}));
    await panel.fire('click',button({action:'megablock'}));
    assert.equal(jobCount,2);
    await panel.fire('click',button({action:'back'}));
    assert.equal(backCount,1);
    assert.ok(dispatched>0);
    assert.ok(fetchCount>=2);
    instance.dispose();
    assert.equal(root.childNodes.length,0);
    const second=mountOpportunityPanel(host,{apiBase:'//external.invalid'});
    await tick();
    assert.match(root.childNodes[1].querySelector('[role=status]').textContent,/SAME_ORIGIN_API_REQUIRED/);
    second.dispose();
  } finally {
    for(const [k,v] of Object.entries(original))globalThis[k]=v;
  }
});
