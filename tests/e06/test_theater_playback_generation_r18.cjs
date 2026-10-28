'use strict';
// E06 W2·02 R18: focused SOURCE-only WebView2 theater playback epoch tests.
// NOT a Windows, installer, or E07 acceptance.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=readFileSync(path.resolve(__dirname,'../../integrations/creative/web/theater.js'),'utf8');
function mount(){
 const listeners={};let playImpl=()=>Promise.resolve();let n=0;
 const video={
  src:'',style:{},load(){},pause(){},play(){return playImpl()},
  removeAttribute(k){if(k==='src')this.src=''},
  addEventListener(k,fn){(listeners[k]??=[]).push(fn)},
  removeEventListener(k,fn){listeners[k]=(listeners[k]||[]).filter(f=>f!==fn)}
 };
 const ids={video,poster:{style:{}},stage:{},status:{textContent:''},
  file:{},subtitles:{},play:{},pause:{},full:{},screens:{},
  title:{textContent:''},space:{textContent:''}};
 const document={getElementById:k=>ids[k],fullscreenElement:null,
  exitFullscreen:async()=>{}};
 const window={location:{search:''},addEventListener(){}};
 const URL={createObjectURL:()=> 'blob:epoch-'+(++n),revokeObjectURL(){}};
 const sandbox={document,window,URL,URLSearchParams,Blob};
 vm.runInNewContext(source+'\n;globalThis.__r18={chooseVideo,play,pause}',sandbox,
  {filename:'theater.js',timeout:2000});
 return {api:sandbox.__r18,ids,setPlay:fn=>playImpl=fn,
  fire:k=>(listeners[k]||[]).forEach(fn=>fn())};
}
test('delayed play success cannot overwrite newer selected video status',async()=>{
 const h=mount();h.api.chooseVideo({name:'one.mp4'});
 let resolve;h.setPlay(()=>new Promise(r=>{resolve=r}));
 const p=h.api.play();h.api.chooseVideo({name:'two.mp4'});resolve();await p;
 assert.match(h.ids.status.textContent,/two.mp4/);
});
test('delayed play rejection cannot overwrite explicit Pause',async()=>{
 const h=mount();h.api.chooseVideo({name:'one.mp4'});
 let reject;h.setPlay(()=>new Promise((_,r)=>{reject=r}));
 const p=h.api.play();h.api.pause();reject(Error('aborted'));await p;
 assert.equal(h.ids.status.textContent,'Пауза');
});
test('delayed play success cannot overwrite media decode failure',async()=>{
 const h=mount();h.api.chooseVideo({name:'broken.mp4'});
 let resolve;h.setPlay(()=>new Promise(r=>{resolve=r}));
 const p=h.api.play();h.fire('error');resolve();await p;
 assert.match(h.ids.status.textContent,/повреждено/);
});
test('current successful play status still works',async()=>{
 const h=mount();h.api.chooseVideo({name:'good.mp4'});await h.api.play();
 assert.equal(h.ids.status.textContent,'Воспроизведение');
});
test('current play rejection still provides meaningful error',async()=>{
 const h=mount();h.api.chooseVideo({name:'good.mp4'});
 h.setPlay(()=>Promise.reject(Error('denied')));await h.api.play();
 assert.match(h.ids.status.textContent,/denied/);
});
