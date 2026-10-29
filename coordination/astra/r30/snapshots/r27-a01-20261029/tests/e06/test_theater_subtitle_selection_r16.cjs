'use strict';
// E06 W2·02 R16, existing WebView2 theater source; these are Node-only behavior checks.
// This test suite is not a native Windows/WPF or independent E07 acceptance.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=readFileSync(path.resolve(__dirname,'../../integrations/creative/web/theater.js'),'utf8');
const srt='1\n00:00:01,000 --> 00:00:02,000\nCaption';
function theater(){
 let n=0;const revoked=[];
 const video={src:'',style:{},children:[],addEventListener(){},load(){},pause(){},
  play(){return Promise.resolve()},removeAttribute(x){if(x==='src')this.src=''},
  appendChild(node){this.children.push(node)}};
 const ids={video,poster:{style:{}},stage:{requestFullscreen(){return Promise.resolve()}},
  status:{textContent:''},file:{value:'picked'},subtitles:{value:'picked'},play:{},pause:{},
  full:{},screens:{},title:{textContent:''},space:{textContent:''}};
 const document={getElementById:id=>ids[id],createElement(){return {track:{mode:'hidden'},
  addEventListener(){},remove(){video.children=video.children.filter(x=>x!==this)}}},
  fullscreenElement:null,exitFullscreen(){return Promise.resolve()}};
 const window={location:{search:''},addEventListener(){}};
 const URL={createObjectURL(){return 'blob:r16-'+(++n)},revokeObjectURL(u){revoked.push(u)}};
 const sandbox={document,window,URL,URLSearchParams,Blob};
 vm.runInNewContext(source+'\n;globalThis.__api={chooseSubtitle,chooseVideo}',sandbox,
  {filename:'theater.js',timeout:2000});
 return {api:sandbox.__api,ids,video,revoked};
}
test('previous captions detach immediately while another caption read is pending',async()=>{
 const h=theater();await h.api.chooseSubtitle({name:'old.srt',size:100,text:async()=>srt});
 let resolve;const blocked=new Promise(r=>{resolve=r});
 const newer=h.api.chooseSubtitle({name:'new.srt',size:100,text:()=>blocked});
 assert.equal(h.video.children.length,0,'stale captions must not remain visible');
 resolve(srt);await newer;
 assert.equal(h.video.children.length,1);assert.equal(h.video.children[0].label,'new.srt');
});
test('oversize subtitle selection clears already playing old captions',async()=>{
 const h=theater();await h.api.chooseSubtitle({name:'old.srt',size:100,text:async()=>srt});
 await h.api.chooseSubtitle({name:'huge.srt',size:2*1024*1024+1,text:async()=>srt});
 assert.equal(h.video.children.length,0);assert.equal(h.revoked.length,1);
 assert.match(h.ids.status.textContent,/2 МиБ/);
});
test('malformed replacement does not leave previous caption track active',async()=>{
 const h=theater();await h.api.chooseSubtitle({name:'old.srt',size:100,text:async()=>srt});
 await h.api.chooseSubtitle({name:'bad.vtt',size:50,text:async()=> 'NOT_WEBVTT'});
 assert.equal(h.video.children.length,0);assert.match(h.ids.status.textContent,/не подключены/);
});
test('file pickers clear values so identical files can be selected again',async()=>{
 const h=theater();
 h.ids.file.files=[{name:'again.mp4'}];h.ids.file.onchange({target:h.ids.file});
 h.ids.subtitles.files=[{name:'again.srt',size:100,text:async()=>srt}];
 h.ids.subtitles.onchange({target:h.ids.subtitles});
 assert.equal(h.ids.file.value,'');assert.equal(h.ids.subtitles.value,'');
});
