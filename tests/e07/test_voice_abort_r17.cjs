'use strict';
// SOURCE-only QA: fake DOM/MediaRecorder events, NOT genuine microphone/ASR/TTS.
const {readFileSync}=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const path=require('node:path');
const source=readFileSync(process.argv[2]||path.resolve(__dirname,'../../proposals/NOX-VOICE-LAB/voice-lab.js'),'utf8');
class E{
 constructor(tag){this.tag=tag;this.nodeType=1;this.children=[];this.value='';this.textContent='';}
 append(...v){for(const e of v){this.children.push(e);if(this.tag==='select'&&this.children.length===1)this.value=e.value;}}
 replaceChildren(...v){this.children=[];this.value='';this.append(...v);}
 setAttribute(){} remove(){}
}
function find(e,text){if(e.tag==='button'&&e.textContent===text)return e;for(const c of e.children){const found=find(c,text);if(found)return found;}return null;}
function setup(pending=false){
 const handlers=new Map(),calls=[];let rec=null,grant;
 const tracks=[{stop(){this.stopped=true;}}],stream={getTracks:()=>tracks};
 const document={hidden:false,createElement:t=>new E(t),addEventListener:(t,f)=>handlers.set(t,f),removeEventListener:t=>handlers.delete(t)};
 const navigator={mediaDevices:{getUserMedia:()=>pending?new Promise(r=>grant=r):Promise.resolve(stream)}};
 class MR{constructor(s,o={}){this.state='inactive';this.mimeType=o.mimeType||'audio/webm';rec=this;}
 static isTypeSupported(){return true;}
 start(){this.state='recording';}
 stop(){this.state='inactive';this.ondataavailable?.({data:new Blob(['user-audio'])});this.onstop?.();}}
 const module={exports:{}};
 vm.runInNewContext(source,{module,document,navigator,MediaRecorder:MR,Blob,Promise,setTimeout:()=>1,clearTimeout:()=>{}},{timeout:2000});
 const root=new E('main'),api=module.exports.mount(root,{onAudio:a=>{calls.push(a);return Promise.resolve();},dispatch:()=>Promise.resolve({})});
 return {api,calls,document,tracks,handlers,record:find(root,'Записать 30 секунд'),stop:find(root,'STOP'),rec:()=>rec,grant:()=>grant(stream)};
}
const cases={
 async normal(){const h=setup();await h.record.onclick();h.rec().stop();assert.equal(h.calls.length,1);h.api.destroy();},
 async stop(){const h=setup();await h.record.onclick();h.stop.onclick();assert.equal(h.calls.length,0,'STOP submitted audio');assert(h.tracks[0].stopped);h.api.destroy();},
 async hidden(){const h=setup();await h.record.onclick();h.document.hidden=true;h.handlers.get('visibilitychange')();assert.equal(h.calls.length,0,'hidden tab submitted audio');assert(h.tracks[0].stopped);h.api.destroy();},
 async latePermission(){const h=setup(true),p=h.record.onclick();h.document.hidden=true;h.handlers.get('visibilitychange')();h.grant();await p;assert.equal(h.rec(),null,'recording started while hidden');assert(h.tracks[0].stopped);h.api.destroy();},
};
(async()=>{let passed=0;for(const [name,test] of Object.entries(cases)){try{await test();console.log('PASS',name);passed++;}catch(e){console.log('FAIL',name,String(e.message));}}
 console.log(`RESULT ${passed}/${Object.keys(cases).length}`);if(passed!==Object.keys(cases).length)process.exitCode=1;})();
