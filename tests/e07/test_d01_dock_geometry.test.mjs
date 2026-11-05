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
 getClientRects(){return [this.rect]},getBoundingClientRect(){return this.rect},closest(){return null},contains(o){return o===this},
 getAttribute(k){return ({id:'nox-express-primary-'+n.toLowerCase(),'data-nox-primary':n,'aria-label':n})[k]??null;},hasAttribute(){return false;}}));
 const nav={isConnected:true,closest(){return null},getClientRects(){return [1]},querySelectorAll(){return buttons;}};
 const document={documentElement:{clientWidth:width,clientHeight:change.noheight?0:480},querySelectorAll(){return [buttons[0]];},
 elementFromPoint(x,y){if(change.overlay)return {tagName:'DIV'};return buttons.find(o=>x>=o.rect.left&&x<=o.rect.right&&y>=o.rect.top&&y<=o.rect.bottom)??null;}};
 const window={getComputedStyle(){return {display:'grid',visibility:'visible',pointerEvents:'auto',opacity:1};}};
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
