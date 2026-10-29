import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
const source=readFileSync(new URL('./loader.mjs',import.meta.url),'utf8')
 .replace(/^import .+;\s*$/gm,'').replace('export const ownerAudit=','const ownerAudit=');
function fixture({reduced=false,noMedia=false,legacy=false,bodyClass=''}={}){
 const nodes=[];
 class El{constructor(tag){this.tag=tag;this.id='';this.value='';this.dataset={};this.children=[];this.className='';this.textContent='';this.classList={contains:v=>v===bodyClass};}
 append(...xs){this.children.push(...xs);}appendChild(x){this.children.push(x);}closest(){return null;}}
 const screen=new El('div');screen.id='screen-immersive';nodes.push(screen);
 const document={body:new El('body'),readyState:'complete',createElement(tag){let e=new El(tag);nodes.push(e);return e;},getElementById(id){return nodes.find(x=>x.id===id)||null;},addEventListener(){}};
 const callbacks=[],motion=noMedia?null:{matches:reduced};
 if(motion){if(legacy)motion.addListener=fn=>callbacks.push(fn);else motion.addEventListener=(_,fn)=>callbacks.push(fn);}
 const window={location:{origin:'https://nox.local'},matchMedia:noMedia?undefined:()=>motion};window.parent=window;
 const out={mount:null,scene:[],motion:[],pack:[],preview:[]};
 const mountUnifiedCinema=(_,options)=>{out.mount=options;return {setReducedMotion:v=>out.motion.push(v),setMode:v=>{out.scene.push(v);return true;},preview:id=>{out.preview.push(id);return {name:'FX'};},current:()=>({active:out.scene.at(-1)||options.mode})}};
 const mountCinematic=()=>({decorate(){},setMode:v=>out.pack.push(v)});
 const fetch=()=>Promise.resolve({ok:true,json:()=>Promise.resolve({version:'NOX-INTEGRATION-PACK-01',actions:Array.from({length:50},(_,i)=>({taskId:'NIP01-'+String(i+1).padStart(2,'0'),routeId:'route'+i,title:'Route '+i,category:'chat',owner:1}))})});
 runInNewContext(source,{document,window,fetch,mountUnifiedCinema,mountCinematic,reviewWowScopes:()=>{},CUES:[],SHOTS:[],COMPOSITIONS:[]},{timeout:1000});
 return {out,find:id=>document.getElementById(id),async ready(){for(let i=0;i<7;i++)await Promise.resolve();},
 reduced(v){motion.matches=v;callbacks.forEach(cb=>cb({matches:v}));}};
}
test('E01-W2-R14-01 initial scene forced REDUCED by OS',()=>{const x=fixture({reduced:true,bodyClass:'mode-max'});assert.equal(x.out.mount.mode,'REDUCED');assert.equal(x.out.mount.reducedMotion,true);});
test('E01-W2-R14-02 delayed PACK01 forced reduced by OS',async()=>{const x=fixture({reduced:true});await x.ready();assert.equal(x.out.pack[0],'reduced');});
test('E01-W2-R14-03 MAX selector cannot override reduced scene',async()=>{const x=fixture({reduced:true});await x.ready();x.find('nox-wow200-mode').value='MAX';x.find('nox-wow200-mode').onchange();assert.equal(x.out.scene.at(-1),'REDUCED');});
test('E01-W2-R14-04 MAX selector cannot override reduced PACK01',async()=>{const x=fixture({reduced:true});await x.ready();x.find('nox-wow200-mode').value='MAX';x.find('nox-wow200-mode').onchange();assert.equal(x.out.pack.at(-1),'reduced');});
test('E01-W2-R14-05 preview protects and truthfully labels reduced mode',async()=>{const x=fixture({reduced:true});await x.ready();x.find('nox-wow200-mode').value='MAX';x.find('nox-wow200-id').value='51';x.find('nox-wow200-preview').onclick();assert.equal(x.out.scene.at(-1),'REDUCED');assert.match(x.find('nox-wow200-state').textContent,/режим REDUCED/);});
test('E01-W2-R14-06 OS reduces OFF restores chosen MAX in both engines',async()=>{const x=fixture({reduced:true});await x.ready();x.find('nox-wow200-mode').value='MAX';x.reduced(false);assert.equal(x.out.scene.at(-1),'MAX');assert.equal(x.out.pack.at(-1),'max');});
test('E01-W2-R14-07 OS reduces ON disables both engines',async()=>{const x=fixture();await x.ready();x.reduced(true);assert.equal(x.out.scene.at(-1),'REDUCED');assert.equal(x.out.pack.at(-1),'reduced');});
test('E01-W2-R14-08 ordinary ECO selector synchronizes scene and PACK01',async()=>{const x=fixture();await x.ready();x.find('nox-wow200-mode').value='ECO';x.find('nox-wow200-mode').onchange();assert.equal(x.out.scene.at(-1),'ECO');assert.equal(x.out.pack.at(-1),'eco');});
test('E01-W2-R14-09 untrusted selector falls back BALANCED',async()=>{const x=fixture();await x.ready();x.find('nox-wow200-mode').value='UNKNOWN';x.find('nox-wow200-mode').onchange();assert.equal(x.out.scene.at(-1),'BALANCED');assert.equal(x.out.pack.at(-1),'balanced');});
test('E01-W2-R14-10 missing and legacy matchMedia remain safe',async()=>{const n=fixture({noMedia:true});await n.ready();assert.equal(n.out.mount.mode,'BALANCED');const l=fixture({legacy:true});await l.ready();l.reduced(true);assert.equal(l.out.scene.at(-1),'REDUCED');assert.equal(l.out.pack.at(-1),'reduced');});

test("R27 loader releases the explicit startup reduced override",async()=>{const x=fixture({reduced:true});await x.ready();x.reduced(false);assert.equal(x.out.motion.at(-1),false);x.reduced(true);assert.equal(x.out.motion.at(-1),true);});
