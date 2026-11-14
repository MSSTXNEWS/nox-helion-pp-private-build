'use strict';
// Source-behavior tests for the existing WPF WebView2 theater (NOT installed Windows E07).
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=readFileSync(path.resolve(__dirname,'../../integrations/creative/web/theater.js'),'utf8');
const srt='1\n00:00:01,000 --> 00:00:02,000\nCaption';
function deferred(){let resolve;const promise=new Promise(r=>{resolve=r});return {promise,resolve}}
function theater(){
 const evt={};const revoked=[];let urlNum=0;
 const video={src:'',style:{},children:[],addEventListener(){},load(){},pause(){},
  play(){return Promise.resolve()},appendChild(node){this.children.push(node)},
  removeAttribute(name){delete this[name]}};
 const elements={video,poster:{style:{}},stage:{requestFullscreen(){return Promise.resolve()}},
  status:{textContent:''},file:{},subtitles:{},play:{},pause:{},full:{},screens:{},
  title:{textContent:''},space:{textContent:''}};
 const document={getElementById(id){return elements[id]},
  createElement(){return {kind:'track',track:{mode:'hidden'},
    addEventListener(event,handler){this['on'+event]=handler},
    remove(){video.children=video.children.filter(node=>node!==this)}}},
  fullscreenElement:null,exitFullscreen(){return Promise.resolve()}};
 const window={location:{search:''},addEventListener(name,handler){evt[name]=handler}};
 const mockURL={createObjectURL(){return 'blob:test-'+(++urlNum)},revokeObjectURL(u){revoked.push(u)}};
 const sandbox={document,window,URL:mockURL,URLSearchParams,Blob};
 vm.runInNewContext(source+'\n;globalThis.__api={chooseVideo,chooseSubtitle,toWebVtt}',sandbox,
  {filename:'theater.js',timeout:2000});
 return {api:sandbox.__api,video,elements,events:evt,revoked};
}
test('new video removes previous subtitle track and revokes its URL',async()=>{
 const h=theater();await h.api.chooseSubtitle({name:'old.srt',size:100,text:async()=>srt});
 assert.equal(h.video.children.length,1);h.api.chooseVideo({name:'next.mp4'});
 assert.equal(h.video.children.length,0);assert.ok(h.revoked.includes('blob:test-1'));
});
test('slow earlier subtitle never overrides the later selection',async()=>{
 const h=theater(),a=deferred(),b=deferred();
 const first=h.api.chooseSubtitle({name:'old.srt',size:100,text:()=>a.promise});
 const second=h.api.chooseSubtitle({name:'new.srt',size:100,text:()=>b.promise});
 b.resolve(srt);await second;a.resolve(srt);await first;
 assert.equal(h.video.children.length,1);assert.equal(h.video.children[0].label,'new.srt');
});
test('video replacement cancels an in-flight subtitle read',async()=>{
 const h=theater(),a=deferred();
 const first=h.api.chooseSubtitle({name:'old.srt',size:100,text:()=>a.promise});
 h.api.chooseVideo({name:'new.mp4'});a.resolve(srt);await first;
 assert.equal(h.video.children.length,0);
});
test('stale track load callback cannot enable captions on replacement track',async()=>{
 const h=theater();
 await h.api.chooseSubtitle({name:'a.srt',size:100,text:async()=>srt});
 const old=h.video.children[0];
 await h.api.chooseSubtitle({name:'b.srt',size:100,text:async()=>srt});
 const current=h.video.children[0];old.onload();assert.equal(current.track.mode,'hidden');
 current.onload();assert.equal(current.track.mode,'showing');
});
test('beforeunload invalidates pending reads and releases resources',async()=>{
 const h=theater(),a=deferred();
 const pending=h.api.chooseSubtitle({name:'a.srt',size:100,text:()=>a.promise});
 h.events.beforeunload();a.resolve(srt);await pending;
 assert.equal(h.video.children.length,0);
});
test('SRT remains converted to parseable WebVTT timestamps',()=>{
 const h=theater();assert.ok(h.api.toWebVtt(srt,'sample.srt').includes('00:00:01.000 --> 00:00:02.000'));
});
