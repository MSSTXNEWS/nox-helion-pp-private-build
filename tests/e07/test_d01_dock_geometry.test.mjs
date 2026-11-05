// D01: actual verifiedOriginalPrimaryDock JS extracted from immutable R11 Python stage.
// Run: node --test tests/e07/test_d01_dock_geometry.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const src=readFileSync(new URL('../../coordination/express/stage_original_five_primary.py',import.meta.url),'utf8');
const a=src.indexOf('function verifiedOriginalPrimaryDock(){');
const b=src.indexOf("\nnav.addEventListener('click'",a);
assert.ok(a>=0&&b>a,'original live UIA handler exists');
const fn=src.slice(a,b);
const names=['CHAT','INSTALL','MODELS','LEARN','SETTINGS'];
function evaluate(width,change={}){
 const rects=names.map((_,i)=>{const cell=(width-40)/5,left=20+i*cell;return {left,top:370,right:left+cell-5,bottom:426,width:cell-5,height:56};});
 if(change.offscreen){const r=rects[4];r.right=width+12;r.width=r.right-r.left;}
 if(change.overlap){rects[1]={...rects[0],left:rects[0].left+4,right:rects[0].right+4};}
 if(change.fractional){const r=rects[4];r.right=width+.25;r.width=r.right-r.left;}
 const buttons=names.map((n,i)=>({tagName:'BUTTON',isConnected:true,disabled:false,hidden:false,tabIndex:0,rect:rects[i],
 getClientRects(){return [this.rect]},getBoundingClientRect(){return this.rect},
 closest(sel){return change.ariaDisabledButton&&i===2&&sel.includes('aria-disabled')?this:null;},contains(o){return o===this},
 getAttribute(k){return ({id:'nox-express-primary-'+n.toLowerCase(),'data-nox-primary':n,'aria-label':n,
 type:change.badTypeIndex===i?change.badTypeValue:'button'})[k]??null;},hasAttribute(){return false;}}));
 const originalShell={parentElement:null,hidden:change.outerHidden===true,inert:change.outerInert===true,
 getAttribute(k){return change.outerAriaDisabled&&k==='aria-disabled'?'true':null;}};
 const nav={isConnected:true,parentElement:change.outerShell?originalShell:null,
 closest(sel){return change.ariaDisabledAncestor&&sel.includes('aria-disabled')?this:null;},getClientRects(){return [1]},querySelectorAll(){return buttons;}};
 const document={documentElement:{clientWidth:width,clientHeight:change.noheight?0:480},querySelectorAll(){return [buttons[0]];},
 elementFromPoint(x,y){if(change.overlay)return {tagName:'DIV'};return buttons.find(o=>x>=o.rect.left&&x<=o.rect.right&&y>=o.rect.top&&y<=o.rect.bottom)??null;}};
 const window={getComputedStyle(node){
 const outer=node===originalShell;
 return {display:outer&&change.outerDisplayNone?'none':'grid',
 visibility:outer&&change.outerVisibilityHidden?'hidden':'visible',
 pointerEvents:outer&&change.outerPointerBlocked?'none':'auto',
 opacity:outer&&change.outerOpacityZero?'0':outer&&change.outerOpacityInvalid?'unavailable':'1'};
 }};
 return new Function('nav','window','document','originalPrimaryButtons',fn+';return verifiedOriginalPrimaryDock();')(nav,window,document,buttons);
}
test('D02 original five UIA controls remain inside compact/desktop viewports',()=>{
 for(const width of [320,390,551,800,1044])assert.equal(evaluate(width),true,width);
});
test('D02 UIA rejects clipped, overlapping and covered primary controls',()=>{
 for(const change of [{offscreen:true},{overlap:true},{overlay:true},{noheight:true}])
   assert.equal(evaluate(390,change),false,JSON.stringify(change));
});
test('D02 fractional zoom tolerance does not alter approved design',()=>{
 assert.equal(evaluate(320,{fractional:true}),true);
});

test('D01 prevents UIA access to ARIA-disabled primary dock controls',()=>{
 assert.equal(evaluate(320,{ariaDisabledButton:true}),false);
 assert.equal(evaluate(390,{ariaDisabledAncestor:true}),false);
});
const ownerStart=src.indexOf('function visibleOriginalOwnerTarget(button){');
const ownerEnd=src.indexOf("\nnav.addEventListener('click'",ownerStart);
assert.ok(ownerStart>=0&&ownerEnd>ownerStart,'original R11 owner guard available');
const ownerFn=src.slice(ownerStart,ownerEnd);
function ownerTarget(change={}){
 const r={left:20,top:50,right:change.offscreen?345:140,bottom:110,width:change.offscreen?325:120,height:60};
 const b={tagName:'BUTTON',isConnected:true,disabled:!!change.disabled,
   closest(sel){return change.ariaDisabled&&sel.includes('aria-disabled')?this:null},
   getClientRects(){return [r]},getBoundingClientRect(){return r},contains(el){return el===this}};
 const d={documentElement:{clientWidth:320,clientHeight:480},elementFromPoint(){return change.overlay?{}:b}};
 const w={getComputedStyle(){return {display:'block',visibility:'visible',
 pointerEvents:change.pointerBlocked?'none':'auto',opacity:change.transparent?'0':'1'}}};
 return new Function('button','document','window',ownerFn+';return visibleOriginalOwnerTarget(button)')(b,d,w);
}
test('D01 native original handler only receives physically pressable source control',()=>{
 assert.equal(ownerTarget(),true);
 for(const key of ['disabled','ariaDisabled','offscreen','overlay','transparent','pointerBlocked'])
   assert.equal(ownerTarget({[key]:true}),false,key);
});

test('D01 refuses invisible ancestor shells even when the original five DOM/UIA hit targets remain visible',()=>{
 for(const change of [
  {outerOpacityZero:true},{outerOpacityInvalid:true},{outerPointerBlocked:true},
  {outerDisplayNone:true},{outerVisibilityHidden:true},{outerHidden:true},
  {outerInert:true},{outerAriaDisabled:true}
 ])assert.equal(evaluate(390,{outerShell:true,...change}),false,JSON.stringify(change));
 assert.equal(evaluate(390,{outerShell:true}),true);
});

test('D01 rejects mutated submit, reset and absent button type without changing HOME styling',()=>{
 assert.equal(evaluate(390),true);
 for(const badTypeValue of ['submit','reset',null])
   assert.equal(evaluate(390,{badTypeIndex:2,badTypeValue}),false,String(badTypeValue));
 assert.ok(src.includes('event.preventDefault();'),'trusted primary gesture suppresses form defaults');
});
