'use strict';
// E06 W2·02 media-error lifecycle, source-only Node tests (NOT Windows E07).
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=readFileSync(path.resolve(__dirname,'../../integrations/creative/web/theater.js'),'utf8');
function create(search=''){
 let count=0;const listeners={};const revoked=[];
 const video={src:'',style:{},children:[],load(){},pause(){},play(){return Promise.resolve()},
  removeAttribute(name){if(name==='src')this.src=''},appendChild(x){this.children.push(x)},
  addEventListener(name,cb,opts){(listeners[name]??=[]).push({cb,once:opts?.once})},
  removeEventListener(name,cb){listeners[name]=(listeners[name]||[]).filter(x=>x.cb!==cb)},
  dispatch(name){for(const listener of [...(listeners[name]||[])]){
   if(!(listeners[name]||[]).includes(listener))continue;
   listener.cb({type:name});if(listener.once)this.removeEventListener(name,listener.cb);
  }}
 };
 const elements={video,poster:{style:{}},stage:{requestFullscreen(){return Promise.resolve()}},
  status:{textContent:''},file:{},subtitles:{},play:{},pause:{},full:{},screens:{},title:{textContent:''},space:{textContent:''}};
 const document={getElementById:id=>elements[id],createElement(kind){return {kind,track:{mode:'hidden'},
  addEventListener(){},remove(){video.children=video.children.filter(x=>x!==this)}}},
  fullscreenElement:null,exitFullscreen(){return Promise.resolve()}};
 const window={location:{search},addEventListener(){}};
 const URL={createObjectURL(){return 'blob:test'+(++count)},revokeObjectURL(url){revoked.push(url)}};
 const sandbox={document,window,URL,URLSearchParams,Blob};
 vm.runInNewContext(source+'\n;globalThis.__test={chooseVideo,chooseSubtitle}',sandbox,{filename:'theater.js',timeout:2000});
 return {video,elements,revoked,api:sandbox.__test};
}
test('missing trusted project movie keeps poster and gives correct guidance',()=>{
 const h=create('?local_project_media=1&project=clip');
 assert.match(h.video.src,/nox-projects\.invalid/);h.video.dispatch('error');
 assert.match(h.elements.status.textContent,/ещё не готов/);
 assert.equal(h.elements.poster.style.display,'block');
});
test('switching away from mapped movie disarms stale native error handler',()=>{
 const h=create('?local_project_media=1&project=clip');
 h.api.chooseVideo({name:'bad.mov'});h.video.dispatch('error');
 assert.match(h.elements.status.textContent,/Локальное видео/);
 assert.doesNotMatch(h.elements.status.textContent,/ещё не готов/);
});
test('unsupported local movie revokes its blob and clears the broken video',()=>{
 const h=create();h.api.chooseVideo({name:'broken.mp4'});h.video.dispatch('error');
 assert.deepEqual(h.revoked,['blob:test1']);assert.equal(h.video.src,'');
 assert.equal(h.video.style.display,'none');assert.equal(h.elements.poster.style.display,'block');
});
test('after a failed local file selection the user can choose another',()=>{
 const h=create();h.api.chooseVideo({name:'bad.mov'});h.video.dispatch('error');
 h.api.chooseVideo({name:'valid.mp4'});
 assert.equal(h.video.src,'blob:test2');assert.equal(h.elements.poster.style.display,'none');
});

test('local decode failure invalidates an in-flight subtitle read',async()=>{
 const h=create();let release;const pendingText=new Promise(resolve=>{release=resolve});
 h.api.chooseVideo({name:'bad.mp4'});
 const pending=h.api.chooseSubtitle({name:'old.srt',size:100,text:()=>pendingText});
 h.video.dispatch('error');release('1\\n00:00:01,000 --> 00:00:02,000\\nCaption');await pending;
 assert.equal(h.video.children.length,0);
});
test('local decode failure removes active captions and releases both object URLs',async()=>{
 const h=create();h.api.chooseVideo({name:'bad.mp4'});
 await h.api.chooseSubtitle({name:'old.srt',size:100,text:async()=> '1\\n00:00:01,000 --> 00:00:02,000\\nCaption'});
 assert.equal(h.video.children.length,1);h.video.dispatch('error');
 assert.equal(h.video.children.length,0);
 assert.deepEqual(h.revoked,['blob:test2','blob:test1']);
});
