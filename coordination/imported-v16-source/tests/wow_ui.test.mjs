import test from 'node:test';import assert from 'node:assert/strict';
import {previewDesign,NOX_MENU_SECTIONS} from '../ui/selfbuilder-wow-workbench.mjs';
const variants=[1,2,3].map(i=>({id:'v'+i,title:'Эскиз '+i,layout:['ORBITAL','CINEMATIC','WORKSPACE'][i-1],screens:[{section:'РАБОТА',title:'Рабочая среда',route_id:'commands',buttons:[{label:'Новая кнопка',action_id:'new-button',status:'CONTRACT_REQUIRED'}]}]}));
const mk=()=>({schema:'NOX-WOW-DESIGN-REVIEW-v1',state:'OWNER_REVIEW_REQUIRED',proposal_sha256:'a'.repeat(64),variants});
test('canonical eight sections only',()=>assert.equal(NOX_MENU_SECTIONS.length,8));
test('three source proposal candidates',()=>assert.equal(mk().variants.length,3));
test('preview nonlive',()=>assert.equal(previewDesign(mk(),'v2').notLive,true));
test('proposed button not executed',()=>assert.equal(previewDesign(mk(),'v1').screens[0].buttons[0].state,'CONTRACT_REQUIRED'));
test('new ninth menu rejected',()=>{const p=mk();p.variants[0].screens[0].section='НЕКАНОН';assert.throws(()=>previewDesign(p,'v1'))});
test('unknown layout rejected',()=>{const p=mk();p.variants[0].layout='NEW';assert.throws(()=>previewDesign(p,'v1'))});
test('unverified LIVE button rejected',()=>{const p=mk();p.variants[0].screens[0].buttons[0].status='VERIFIED';assert.throws(()=>previewDesign(p,'v1'))});
test('unsafe id rejected',()=>{const p=mk();p.variants[0].screens[0].buttons[0].action_id='../../exe';assert.throws(()=>previewDesign(p,'v1'))});
test('unknown proposal id rejected',()=>assert.throws(()=>previewDesign(mk(),'v4')));
test('unreviewed proposal rejected',()=>{const p=mk();p.state='DRAFT';assert.throws(()=>previewDesign(p,'v1'))});
import {backgroundToggleState} from '../ui/selfbuilder-wow-workbench.mjs';
const bg = (enabled,status=enabled?'ON':'OFF')=>({schema:'NOX-SELFBUILDER-BACKGROUND-v1',source:'ORIGINAL_S03',enabled,revision:3,status,auto_code:false,auto_merge:false,auto_install:false});
test('background defaults HOLD unless S03 proves status',()=>assert.equal(backgroundToggleState(null).ready,false));
test('background OFF correctly labelled',()=>assert.equal(backgroundToggleState(bg(false)).switchLabel,'Включить'));
test('background ON correctly labelled',()=>assert.equal(backgroundToggleState(bg(true)).switchLabel,'Выключить'));
test('background RUNNING is not auto-merge',()=>assert.equal(backgroundToggleState(bg(true,'RUNNING')).label.includes('РАБОТАЕТ'),true));
test('background rejects fake JS local state',()=>assert.equal(backgroundToggleState({...bg(true),source:'localStorage'}).ready,false));
test('background rejects fake installation claim',()=>assert.equal(backgroundToggleState({...bg(true),auto_install:true}).ready,false));
test('background rejects untrusted revision',()=>assert.equal(backgroundToggleState({...bg(true),revision:'3'}).ready,false));

class FakeElement {
 constructor(doc,tag){this.ownerDocument=doc;this.tagName=tag;this.dataset={};this.children=[];
   this.listeners=new Map();this.disabled=false;this.className='';this.textContent='';this.attrs={};}
 append(...children){this.children.push(...children);}
 replaceChildren(...children){this.children=[...children];}
 setAttribute(name,value){this.attrs[name]=value;}
 addEventListener(event,callback){this.listeners.set(event,callback);}
 closest(){return null;}
 querySelector(){return null;}
 remove(){}
}
const fakeRoot=()=>{
 const doc={createElement(tag){return new FakeElement(doc,tag);}};
 return {doc,root:new FakeElement(doc,'root')};
};
const descend=(root,match)=>{
 if(match(root))return root;
 for(const child of root.children||[]){const m=descend(child,match);if(m)return m;}
 return null;
};
import {mountWowDesignWorkbench} from '../ui/selfbuilder-wow-workbench.mjs';
test('background button toggles ONLY via authoritative S03 ON/OFF and readback',async()=>{
 const {doc,root}=fakeRoot();let enabled=false,requests=[];
 const ctrl=mountWowDesignWorkbench({root,documentRef:doc,getProposal:async()=>null,
   ownerApprove:async()=>({state:'HOLD'}),getBackgroundState:async()=>bg(enabled),
   setBackgroundEnabled:async value=>{requests.push(value);enabled=value;return bg(enabled);}});
 const btn=descend(root,x=>x.className==='nox-wow-workbench__background-switch');
 assert.ok(btn);await ctrl.refreshBackground();assert.equal(btn.textContent,'Включить');
 await btn.listeners.get('click')();assert.deepEqual(requests,[true]);assert.equal(btn.textContent,'Выключить');
 assert.equal(btn.attrs['aria-pressed'],'true');
 await btn.listeners.get('click')();assert.deepEqual(requests,[true,false]);assert.equal(btn.textContent,'Включить');
 ctrl.destroy();
});
test('without native background callback, button remains disabled and HOLD',()=>{
 const {doc,root}=fakeRoot();const ctrl=mountWowDesignWorkbench({root,documentRef:doc,
  getProposal:async()=>null,ownerApprove:async()=>({state:'HOLD'})});
 const btn=descend(root,x=>x.className==='nox-wow-workbench__background-switch');
 assert.equal(btn.disabled,true);assert.equal(btn.textContent,'Недоступно');ctrl.destroy();
});