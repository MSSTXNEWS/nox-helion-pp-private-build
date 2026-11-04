/** Original OneHost WOW background switch: negative S03 revision/status receipts. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {backgroundToggleState, mountWowDesignWorkbench} from './selfbuilder-wow-workbench.mjs';

const base = (enabled, status, revision) => ({
  schema:'NOX-SELFBUILDER-BACKGROUND-v1',source:'ORIGINAL_S03',
  enabled,status,revision,auto_code:false,auto_merge:false,auto_install:false
});
class Element {
  constructor(tag,doc){this.tagName=tag;this.ownerDocument=doc;this.dataset={};
    this.children=[];this.listeners=new Map();this.disabled=false;this.className='';}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=[...children];}
  setAttribute(name,value){this[name]=value;}
  addEventListener(name,fn){this.listeners.set(name,fn);}
  querySelector(){return null;}
  closest(){return null;}
  remove(){this.removed=true;}
}
function walk(node){return [node,...node.children.flatMap(walk)];}
async function switchFixture({initial,ack,readback}) {
  const documentRef={createElement(tag){return new Element(tag,this);}};
  const root=new Element('root',documentRef);const errors=[];let reads=0;
  const mounted=mountWowDesignWorkbench({
    root,documentRef,getProposal:async()=>null,ownerApprove:async()=>{throw Error('NO_NATIVE_APPROVAL');},
    getBackgroundState:async()=>++reads===1?initial:readback,
    setBackgroundEnabled:async enabled=>{
      assert.equal(enabled,!initial.enabled);
      return ack;
    },onError:e=>errors.push(e.message)
  });
  for(let i=0;i<4;i++)await Promise.resolve();
  const button=walk(root).find(n=>n.className==='nox-wow-workbench__background-switch');
  assert.ok(button);assert.equal(button.disabled,false);
  await button.listeners.get('click')();
  const result={state:walk(root).find(n=>n.dataset.noxBackgroundControl==='true').dataset.state,
    reads,errors};
  mounted.destroy();return result;
}
test('S03 status must agree with persisted enabled bit, including STOPPING',()=>{
  assert.equal(backgroundToggleState(base(false,'OFF',1)).ready,true);
  assert.equal(backgroundToggleState(base(true,'ON',2)).ready,true);
  assert.equal(backgroundToggleState(base(true,'RUNNING',3)).ready,true);
  assert.equal(backgroundToggleState(base(false,'STOPPING',4)).ready,true);
  for(const x of [base(false,'RUNNING',5),base(true,'OFF',6),
                  base(false,'ON',7),base(true,'STOPPING',8)])
    assert.equal(backgroundToggleState(x).ready,false);
});
test('S03 ACK cannot reuse old revision to fake successful enable',async()=>{
  const got=await switchFixture({initial:base(false,'OFF',11),
    ack:base(true,'ON',11),readback:base(true,'ON',11)});
  assert.equal(got.state,'HOLD');assert.equal(got.reads,1);
  assert.deepEqual(got.errors,['S03_BACKGROUND_SWITCH_NOT_CONFIRMED']);
});
test('S03 readback must not be older than acknowledged CAS revision',async()=>{
  const got=await switchFixture({initial:base(false,'OFF',11),
    ack:base(true,'ON',13),readback:base(true,'ON',12)});
  assert.equal(got.state,'HOLD');assert.equal(got.reads,2);
  assert.deepEqual(got.errors,['S03_BACKGROUND_READBACK_MISMATCH']);
});
test('genuine advanced CAS revision and matching S03 readback remain usable',async()=>{
  const got=await switchFixture({initial:base(false,'OFF',11),
    ack:base(true,'ON',12),readback:base(true,'ON',12)});
  assert.equal(got.state,'ON');assert.equal(got.reads,2);
  assert.deepEqual(got.errors,[]);
});
