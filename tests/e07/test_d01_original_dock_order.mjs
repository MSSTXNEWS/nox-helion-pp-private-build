// D01: execute the original staged R11 HOME dock verifier, not a copied validator.
import {readFileSync} from 'node:fs';
import {strict as assert} from 'node:assert';
import {test} from 'node:test';
const source=readFileSync(new URL('../../coordination/express/stage_original_five_primary.py',import.meta.url),'utf8');
const begin=source.indexOf('function verifiedOriginalPrimaryDock(){');
const end=source.indexOf('function visibleOriginalOwnerTarget(',begin);
assert.ok(begin>0&&end>begin,'original production function must be preserved');
const run=new Function('nav','window','document','originalPrimaryButtons',
  source.slice(begin,end)+';return verifiedOriginalPrimaryDock()');
const names=['CHAT','INSTALL','MODELS','LEARN','SETTINGS'];
function check(placements,width=320){
 const buttons=placements.map((p,i)=>{
  const rect={left:p[0],top:p[1],right:p[0]+p[2],bottom:p[1]+p[3],width:p[2],height:p[3]};
  return {tagName:'BUTTON',isConnected:true,disabled:false,hidden:false,tabIndex:0,rect,
   getAttribute(k){return {id:'nox-express-primary-'+names[i].toLowerCase(),'data-nox-primary':names[i],'aria-label':names[i]}[k]??null},
   hasAttribute(){return false},closest(){return null},getClientRects(){return [{}]},
   getBoundingClientRect(){return rect},contains(){return false}};
 });
 const nav={isConnected:true,closest(){return null},getClientRects(){return [{}]},querySelectorAll(){return buttons}};
 const document={documentElement:{clientWidth:width,clientHeight:700},
  querySelectorAll(s){return buttons.filter(b=>s.includes(b.getAttribute('id')))},
  elementFromPoint(x,y){return buttons.find(b=>x>=b.rect.left&&x<=b.rect.right&&y>=b.rect.top&&y<=b.rect.bottom)||null}};
 const window={getComputedStyle(){return {display:'block',visibility:'visible',pointerEvents:'auto',opacity:'1'}}};
 return run(nav,window,document,buttons);
}
const five=[[10,100,50,56],[70,100,50,56],[130,100,50,56],[190,100,50,56],[250,100,50,56]];
test('original D02 320px five dock accepted in UIA reading order',()=>assert.equal(check(five),true));
test('original D02 rejects reversed visual order with same DOM tab order',()=>assert.equal(check([[10,100,50,56],[130,100,50,56],[70,100,50,56],[190,100,50,56],[250,100,50,56]]),false));
test('original D02 accepts compact 3+2 adaptive wrap without enforcing a single row',()=>assert.equal(check([[10,100,90,56],[110,100,90,56],[210,100,90,56],[10,170,90,56],[110,170,90,56]]),true));
test('original D02 rejects overlapping/misaligned visual rows',()=>assert.equal(check([[10,100,50,56],[70,120,50,56],[130,120,50,56],[190,120,50,56],[250,120,50,56]]),false));
test('original D02 rejects out-of-viewport hit targets',()=>assert.equal(check([[10,100,50,56],[70,100,50,56],[130,100,50,56],[190,100,50,56],[300,100,50,56]]),false));
