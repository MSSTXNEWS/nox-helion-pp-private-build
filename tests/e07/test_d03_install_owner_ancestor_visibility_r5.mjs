// D03: real original R11 INSTALL/LEARN owner target must not be CSS-hidden
// behind a transparent or hit-disabled ancestor. SOURCE_ONLY, not Windows E07.
import {readFileSync} from 'node:fs';
import {strict as assert} from 'node:assert';
import {test} from 'node:test';
const source=readFileSync(new URL('../../coordination/express/stage_original_five_primary.py',import.meta.url),'utf8');
const begin=source.indexOf('function visibleOriginalOwnerTarget(button){');
const end=source.indexOf("\n\nnav.addEventListener('click',",begin);
assert.ok(begin>0&&end>begin,'original production owner gate required');
const real=new Function('window','document',source.slice(begin,end)+'; return visibleOriginalOwnerTarget;');
const good={display:'block',visibility:'visible',pointerEvents:'auto',opacity:'1'};
function ownerAllowed(ancestorOverrides=[],hitAllowed=true,buttonOverrides={}){
  let chain=null;
  for(const inherited of ancestorOverrides)
    chain={parentElement:chain,_style:{...good,...inherited}};
  const button={tagName:'BUTTON',isConnected:true,disabled:false,parentElement:chain,
    matches:()=>false,getAttribute:()=>null,closest:()=>null,
    getClientRects:()=>[{}],getBoundingClientRect:()=>({
      left:20,right:140,top:15,bottom:80,width:120,height:65}),
    contains:()=>false,_style:{...good,...buttonOverrides}};
  const document={documentElement:{clientWidth:800,clientHeight:600},
    elementFromPoint:()=>hitAllowed?button:null};
  return real({getComputedStyle:el=>el._style},document)(button);
}
test('actual visible original INSTALL owner target allowed',()=>
  assert.equal(ownerAllowed([{},{}]),true));
test('transparent screen parent blocks synthetic native owner click',()=>
  assert.equal(ownerAllowed([{opacity:'0'}]),false));
test('transparent outer ancestor blocks synthetic native owner click',()=>
  assert.equal(ownerAllowed([{}, {opacity:'0'}]),false));
test('pointer-blocked ancestor blocks synthetic native owner click',()=>
  assert.equal(ownerAllowed([{pointerEvents:'none'}]),false));
test('collapsed ancestor and hidden ancestor both block privileged click',()=>{
  assert.equal(ownerAllowed([{display:'none'}]),false);
  assert.equal(ownerAllowed([{visibility:'hidden'}]),false);
});
test('bad computed parent opacity fails closed',()=>
  assert.equal(ownerAllowed([{opacity:'NaN'}]),false));
test('occluded original owner never receives privileged synthetic click',()=>
  assert.equal(ownerAllowed([{}],false),false));
