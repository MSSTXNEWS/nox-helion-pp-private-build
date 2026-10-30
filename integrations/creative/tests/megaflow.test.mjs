// Single Worker-contract regression for B01-B05; no external side effects.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
const source=readFileSync(new URL('../web/five_blocks_megaflow.js',import.meta.url),'utf8');
const sha='a'.repeat(64);
function mount(override={}){
 const ids=new Map(),calls=[];
 const E=(value='')=>({value,textContent:'',children:[],disabled:false,
   append(...x){this.children.push(...x)},setAttribute(){},
   querySelector(){return this}});
 for(const x of ['screen-five','cs5-pipeline','cs5-project','project','cs5-research-query','cs5-text','stop'])ids.set(x,E());
 ids.get('cs5-project').value='creative01';ids.get('cs5-research-query').value='space film';
 ids.get('cs5-text').value='Original user concept';
 const rpc=async(action,payload={})=>{
   calls.push({action,payload});
   if(override[action])return override[action](payload);
   if(action==='cs5_research')return {status:'LIVE_PUBLIC_METADATA_NOT_SALES',items:[{title:'A',source_url:'https://example.org'}]};
   if(action==='cs5_append')return {status:'SAVED_LOCAL_NOT_E11',project_id:'creative01'};
   if(action==='storyboard')return {status:'STORYBOARD_READY',project_id:'creative01',storyboard:{scenes:[1,2,3]}};
   if(action==='create_text')return {status:'CREATED',project_id:'creative01',kind:'sound',bytes:20};
   if(action==='project_files')return {status:'OK',project_id:'creative01',files:[{path:'storyboard.json',bytes:20,sha256:sha}]};
   if(action==='catalog')return {models:[],categories:[]};
   if(action==='cs5_export')return {status:'EXPORTED_LOCAL_NOT_PUBLISHED',project_id:'creative01',bytes:120,sha256:sha};
   if(action==='stop')return {status:'STOPPED'};
   throw Error('unexpected '+action);
 };
 const window={},document={getElementById:id=>ids.get(id)||null,createElement:()=>E()};
 runInNewContext(source,{document,window,rpc,confirm:()=>true,URL});
 const status=()=>ids.get('screen-five').children[0].children[1].textContent;
 return {ids,calls,flow:window.NOXCS5MegaFlow,status};
}
test('all five stages use existing worker, preserve draft and verify receipts',async()=>{
 const x=mount();await x.flow.run();const actions=x.calls.map(c=>c.action);
 assert.equal(x.ids.get('cs5-text').value,'Original user concept');
 assert.equal(actions.filter(x=>x==='cs5_research').length,4);
 assert.equal(actions.filter(x=>x==='cs5_append').length,3);
 assert.ok(actions.includes('catalog')&&!actions.includes('cs5_overview'));
 assert.equal(actions.filter(action=>action==='catalog').length,1);
 assert.ok(!actions.includes('download')&&!actions.includes('publish'));
 assert.ok(x.status().includes('FINISH'));
});
test('no real research data stops without saving',async()=>{
 const x=mount({cs5_research:async()=>{throw Error('offline')}});
 await x.flow.run();assert.equal(x.calls.some(c=>c.action==='cs5_append'),false);
 assert.ok(x.status().includes('B01_NO_PROVIDER_EVIDENCE'));
});
test('missing storyboard file SHA stops before exporting',async()=>{
 const x=mount({project_files:async()=>({status:'OK',files:[]})});
 await x.flow.run();assert.equal(x.calls.some(c=>c.action==='cs5_export'),false);
 assert.ok(x.status().includes('B03_STORYBOARD_FILE_SHA_MISSING'));
});
test('STOP acknowledgement cancels pending stages',async()=>{
 let resolve;const wait=new Promise(r=>{resolve=r});
 const x=mount({cs5_research:async()=>wait});const run=x.flow.run();
 await x.flow.stop();resolve({status:'LIVE_PUBLIC_METADATA_NOT_SALES',items:[]});await run;
 assert.ok(x.status().includes('STOP_ACK: STOPPED'));
 assert.ok(!x.calls.some(c=>c.action==='cs5_append'));
});