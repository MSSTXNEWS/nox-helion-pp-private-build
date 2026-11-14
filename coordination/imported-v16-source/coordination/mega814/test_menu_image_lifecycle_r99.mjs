/** W05 R99: execute canonical MENU10 original lifecycle function, not a mock implementation.
 * Old source fails after late image load/error/promise; no native/E07 claim.
 */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source=readFileSync(new URL('./mega814.mjs',import.meta.url),'utf8');
const start=source.indexOf('function menuWorlds(');
const end=source.indexOf('\nfunction workViews(',start);
assert.ok(start>=0&&end>start,'ORIGINAL_MENU10_FUNCTION_REQUIRED');
const unit=source.slice(start,end)+'\nmenuWorlds';
const ids=['work','intelligence','knowledge','learning','entertainment',
  'people','creative','business','world','pc'];

function check(scenario){
 const all=[];
 function element(tag){
  const o={tag,hidden:false,disabled:false,textContent:'',className:'',
   children:[],dataset:{},style:{},events:{},
   classList:{values:new Set(),add(k){this.values.add(k)},remove(k){this.values.delete(k)},
    contains(k){return this.values.has(k)}},
   append(...items){this.children.push(...items)},
   replaceChildren(...items){this.children=items},
   addEventListener(event,listener){this.events[event]=listener},
   setAttribute(){},querySelector(){return null},after(){},remove(){this.removed=true},click(){}};
  all.push(o);return o;
 }
 const legacyPanel=element('legacy'),menu=element('menu');
 menu.querySelector=()=>({closest:()=>legacyPanel});
 const node=(tag,text,cls)=>{const el=element(tag);el.textContent=text;el.className=cls;return el};
 const note=(parent,msg)=>{const el=node('p',msg);parent.append(el);return el};
 let pending=null;
 const approvedImage=img=>{img.hidden=false;return {then(callback){pending=callback}}};
 const worlds=vm.runInNewContext(unit,{document:{createElement:element},
  node,note,approvedImage,appendMenuV2(){},safeRoute(){},legacy(){return false}},
  {timeout:1000});
 const app=worlds(menu,{worlds:ids.map((id,index)=>({
  id,label:id,legacyIndex:index%8,routes:[]})),asset:{menu10SHA256:'a'.repeat(64)}},
  {available:false},{worlds:[]},null);
 const img=all.find(e=>e.tag==='img');
 const panel=all.find(e=>e.className==='mega814-menu-scene');
 const world=all.find(e=>e.dataset.world==='work');
 const detail=all.find(e=>e.className==='mega814-world-detail');
 assert.ok(img&&panel&&world&&detail&&pending);
 if(scenario==='load-before'){
  img.events.load();assert.equal(legacyPanel.classList.contains('mega814-legacy-hidden'),true);
  app.destroy();assert.equal(legacyPanel.classList.contains('mega814-legacy-hidden'),false);
 }else{
  app.destroy();app.destroy();
  if(scenario==='load-after'){
   img.events.load();assert.equal(legacyPanel.classList.contains('mega814-legacy-hidden'),false);
  }else if(scenario==='error-after'){
   img.events.error();assert.equal(panel.classList.contains('mega814-image-hold'),false);
  }else if(scenario==='promise-after'){
   pending(false);assert.equal(panel.classList.contains('mega814-image-hold'),false);
  }else if(scenario==='click-after'){
   world.events.click();assert.equal(detail.hidden,true);
  }
 }
}
for(const name of ['load-before','load-after','error-after','promise-after','click-after'])check(name);
console.log('MEGA814_ORIGINAL_MENU10_DESTROY_LIFECYCLE_PASS 5/5 SOURCE_ONLY E07_HOLD');
