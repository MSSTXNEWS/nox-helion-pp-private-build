import assert from 'node:assert/strict';
import fs from 'node:fs';
import { validateMenuV2, appendMenuV2 } from './menu-v2-adapter.mjs';
const catalog=JSON.parse(fs.readFileSync(new URL('./menu-v2-193.json',import.meta.url),'utf8'));
const worldIds=catalog.worlds.map(w=>({id:w.id}));
assert.equal(validateMenuV2(catalog,worldIds),catalog);
assert.equal(catalog.worlds.flatMap(w=>w.items).length,193);
for(const mutate of [
  c=>c.worlds[2].items[0].handler_status='E07_ACCEPTED',
  c=>c.worlds[0].items.pop(),
  c=>c.worlds[0].items[0].native_route='admin.deleteAll',
  c=>c.worlds[1].items[0].id='MV2-01-001',
  c=>c.worlds[1].items[0].handler_status='E07_SUCCESS',
  c=>c.source.sha256='0'.repeat(64),
  c=>c.worlds[4].items[0].group={unsafe:'data'}
]){
 const broken=structuredClone(catalog);mutate(broken);
 assert.throws(()=>validateMenuV2(broken,worldIds),/HOLD/);
}
const previous=globalThis.document;
const element=tag=>({tag,children:[],events:{},className:'',textContent:'',hidden:false,value:'',dataset:{},attributes:{},
 append(...nodes){this.children.push(...nodes)},
 replaceChildren(...nodes){this.children=[...nodes]},
 setAttribute(k,v){this.attributes[k]=v},
 addEventListener(k,cb){this.events[k]=cb},
 focus(){this.focused=true},
 click(){this.events.click?.({})}});
globalThis.document={createElement:element};
try {
 let submenus=0, navigable=0, handlers=0;
 for(const w of catalog.worlds){
  const target=element('div');
  const detail=appendMenuV2(target,w,catalog,(route,label)=>{
   handlers++;
   assert.ok(['chat','core-status','model-library'].includes(route));
   const button=element('button');button.textContent=label;button.disabled=true;
   return button;
  });
  assert.equal(detail.tag,'section','MENU V2 uses a static screen, never details/summary dropdown');
  assert.equal(detail.children[0].tag,'h3','World heading is always visible');
  assert.equal(detail.children.some(x=>x.tag==='details'||x.tag==='summary'),false);
  const expected=w.items.length;
  const search=detail.children[1],list=detail.children[2],feature=detail.children[3];
  assert.equal(list.children.length,expected);
  const firstUnverified=list.children.find(row=>{const id=row.children[0].dataset.menuV2Id;return w.items.find(item=>item.id===id)?.native_route===null;});
  assert.ok(firstUnverified,'Each world has at least one navigable item');
  assert.ok(list.children.every(row=>row.children[0].events.click),'193 item navigation independent from native providers');
  assert.ok(list.children.every(row=>row.children[0].disabled!==true),'Never disable MENU navigation');
  assert.equal(firstUnverified.children[0].disabled,undefined);
  firstUnverified.children[0].click();
  assert.equal(feature.hidden,false);
  assert.equal(list.hidden,true);
  assert.ok(feature.children[1].textContent.includes('Прямой исполнитель не подтверждён'));
  feature.children[2].click();
  assert.equal(feature.hidden,true);
  assert.equal(list.hidden,false);
  search.value='NONEXISTENT_CANDIDATE';search.events.input();
  assert.ok(list.children.every(row=>row.hidden));
  search.value='';search.events.input();
  assert.ok(list.children.every(row=>!row.hidden));
  firstUnverified.children[0].click();
  let prevented=false;
  detail.events.keydown({key:'Escape',preventDefault(){prevented=true},stopPropagation(){}});
  assert.ok(prevented&&feature.hidden);
  detail.events.keydown({key:'k',ctrlKey:true,preventDefault(){},stopPropagation(){}});
  assert.equal(search.focused,true);
  assert.equal(target.children.length,1);
  submenus++;navigable+=expected;
 }
 assert.equal(submenus,10);
 assert.equal(navigable,193);
 assert.equal(handlers,0); // All owner actions are lazy, not invoked by menu rendering.
 for(const w of catalog.worlds){
  const nativeItems=w.items.map((item,index)=>({item,index})).filter(x=>x.item.native_route);
  if(!nativeItems.length)continue;
  const target=element('div');
  const detail=appendMenuV2(target,w,catalog,(route,label)=>{
   handlers++;
   const native=element('button');native.disabled=true;native.textContent=label;
   return native;
  });
  const list=detail.children[2],feature=detail.children[3];
  for(const {item,index} of nativeItems){
   const nav=list.children[index].children[0];
   assert.equal(nav.disabled,undefined, 'Offline native must not disable the subsection');
   assert.equal(nav.dataset.menuV2Id,item.id);
   nav.click();
   assert.equal(feature.hidden,false);
   assert.equal(feature.children[3].children[0].disabled,true);
   assert.ok(feature.children[1].textContent.includes('E07 HOLD'));
  }
 }
 assert.equal(handlers,3);
 // An owner adapter may throw when offline/revoked: navigation still opens,
 // while no privileged UI/action is surfaced or falsely marked successful.
 const withNative=catalog.worlds.find(w=>w.items.some(item=>item.native_route));
 const failed=appendMenuV2(element('div'),withNative,catalog,()=>{throw new Error('secret owner failure')});
 const entry=withNative.items.findIndex(item=>item.native_route);
 failed.children[2].children[entry].children[0].click();
 assert.equal(failed.children[3].hidden,false);
 assert.equal(failed.children[3].children[3].children.length,0);
 assert.ok(failed.children[3].children[1].textContent.startsWith('HOLD'));
} finally {globalThis.document=previous}
console.log('NOX_R70_MENU_V2_NAVIGATION_TESTS_PASS 10/10 worlds 193/193 clickable even offline owner routes 3 owner-gated 190 honest HOLD');
