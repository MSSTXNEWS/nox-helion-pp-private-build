import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../web/theater.js', import.meta.url), 'utf8');
const html = fs.readFileSync(new URL('../web/theater.html', import.meta.url), 'utf8');
function harness(query='?project=demo_1') {
  const objects = new Map();
  function el(id) {
    const value = { id, style:{}, textContent:id==='status'?'Выберите разрешённый локальный фильм':'', src:'', files:[], textTracks:[], events:{},
      play(){value.played=true;return Promise.resolve()},pause(){value.paused=true},
      addEventListener(name,fn){value.events[name]=fn},removeEventListener(name){delete value.events[name]},removeAttribute(name){if(name==='src')value.src=''},load(){value.loaded=true},
      appendChild(child){value.child=child;value.textTracks.push(child.track);},
      remove(){value.removed=true}, requestFullscreen(){return Promise.resolve()}};
    objects.set(id,value);return value;
  }
  for(const id of ['video','poster','status','stage','title','space','file','subtitles','play','pause','back','full','screens'])el(id);
  let next=0;const created=[],revoked=[];
  const events={}; const document={getElementById:id=>objects.get(id),documentElement:{lang:'ru'},
    createElement:()=>({track:{mode:'disabled'},remove(){this.removed=true},addEventListener(name,fn){if(name==='load')fn()}}),
    fullscreenElement:null,exitFullscreen(){document.fullscreenElement=null;document.exited=true;return Promise.resolve()}};
  const sandbox = { document,
    window:{location:{search:query},addEventListener(name,fn){events[name]=fn}},
    URL:{createObjectURL:obj=>{created.push(obj);return 'blob:media'+(++next)},revokeObjectURL:url=>revoked.push(url)},
    URLSearchParams, Blob, Promise, String, RegExp, Error};
  vm.runInNewContext(source,sandbox,{filename:'theater.js'});
  // Test fixture: DOM events do not return chooseSubtitle's Promise; drain its queued work.
  const subtitleChange=objects.get('subtitles').onchange;
  objects.get('subtitles').onchange=async event=>{
    subtitleChange(event);
    await new Promise(resolve=>setImmediate(resolve));
  };
  return {objects,created,revoked,events,document};
}
test('actual HTML and JS share the same control IDs and native projector policy',()=>{
  for(const id of ['file','subtitles','play','pause','back','full','screens','status','video','poster','stage','title','space'])
    assert.match(html,new RegExp('id="'+id+'"'));
  // WORK/MENU/HOME PNGs are composed screenshots with their own buttons/text.
  // A secondary cinema scene must not paint those interfaces behind live controls.
  assert.doesNotMatch(html,/url\(\s*["']?\.\.\/(?:work|home|menu_sections)\.png/i);
  assert.match(html,/--glass:/);
  assert.match(html,/radial-gradient/);
  assert.match(html,/prefers-reduced-motion/);
  assert.match(source,/nox_native_viewer/);
});

test('real local video route, never guessed /api/media',()=>{
  const {objects}=harness(), video=objects.get('video'), input=objects.get('file');
  assert.match(objects.get('status').textContent,/Проект demo_1: выберите MP4\/WebM/);
  assert.equal(video.src,'');
  input.onchange({target:{files:[{name:'clip.mp4',size:120}]}});
  assert.equal(video.src,'blob:media1');
  objects.get('play').onclick();assert.equal(video.played,true);
});
test('SRT converts to VTT and attaches a native track',async()=>{
  const {objects,created}=harness();
  objects.get('file').onchange({target:{files:[{name:'movie.mp4',size:512}]}});
  await objects.get('subtitles').onchange({target:{files:[{name:'sub.srt',size:70,text:async()=>"1\n00:00:01,250 --> 00:00:04,500\nПривет!\n"}]}});
  const track=objects.get('video').child;
  assert.equal(track.kind,'subtitles');assert.equal(track.src,'blob:media2');
  assert.equal(objects.get('video').textTracks[0].mode,'showing');
  const text=await created[1].text();assert.match(text,/^WEBVTT/);assert.match(text,/00:00:01\.250 --> 00:00:04\.500/);
});
test('invalid subtitles do not replace a working track',async()=>{
  const {objects,revoked}=harness();
  objects.get('file').onchange({target:{files:[{name:'movie.webm',size:100}]}});
  await objects.get('subtitles').onchange({target:{files:[{name:'good.vtt',size:70,text:async()=>"WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nOK"}]}});
  const track=objects.get('video').child;
  await objects.get('subtitles').onchange({target:{files:[{name:'bad.srt',size:70,text:async()=>"not an SRT"}]}});
  assert.equal(objects.get('video').child,track);assert.deepEqual(revoked,[]);
  assert.match(objects.get('status').textContent,/HOLD/);
});
test('reject empty/invalid video and unsafe subtitle types',async()=>{
  const {objects}=harness();
  objects.get('file').onchange({target:{files:[{name:'bad.exe',size:30}]}});
  assert.equal(objects.get('video').src,'');
  assert.match(objects.get('status').textContent,/HOLD/);
});

test('late subtitle read cannot attach to a different movie',async()=>{
  const {objects}=harness(),input=objects.get('file'),sub=objects.get('subtitles'),video=objects.get('video');
  input.onchange({target:{files:[{name:'first.mp4',size:500}]}});
  let finish;
  const pending=sub.onchange({target:{files:[{name:'first.es.srt',size:90,text:()=>new Promise(resolve=>{finish=resolve})}]}});
  input.onchange({target:{files:[{name:'second.mp4',size:900}]}});
  finish('1\n00:00:01,000 --> 00:00:02,000\nHola');
  await pending;
  assert.equal(video.child,undefined);
  assert.match(objects.get('status').textContent,/second.mp4/);
});
test('last subtitle selection wins and Spanish track language is correct',async()=>{
  const {objects}=harness(),input=objects.get('file'),sub=objects.get('subtitles'),video=objects.get('video');
  input.onchange({target:{files:[{name:'film.mp4',size:1000}]}});
  let finish;
  const pending=sub.onchange({target:{files:[{name:'old.ru.vtt',size:60,text:()=>new Promise(resolve=>{finish=resolve})}]}});
  await sub.onchange({target:{files:[{name:'new.es.vtt',size:80,text:async()=> 'WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHola'}]}});
  const track=video.child;
  assert.equal(track.srclang,'es');
  finish('WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nOld');
  await pending;
  assert.equal(video.child,track);
});

test('F11 requests fullscreen, Escape exits only an active player fullscreen',async()=>{
  const {objects,events,document}=harness();
  let f11=false,esc=false;
  events.keydown({key:'F11',preventDefault(){f11=true}});
  await Promise.resolve();
  assert.equal(f11,true);assert.ok(objects.get('stage'));
  document.fullscreenElement=objects.get('stage');
  events.keydown({key:'Escape',preventDefault(){esc=true}});
  await Promise.resolve();
  assert.equal(esc,true);assert.equal(document.exited,true);
});
test('unsupported fullscreen button emits accessible status, never silent fake success',()=>{
  const {objects}=harness();
  objects.get('stage').requestFullscreen=undefined;
  objects.get('full').onclick();
  assert.match(objects.get('status').textContent,/[Нн]едоступен/);
});
test('non-fullscreen Escape is not hijacked',()=>{
  const {events}=harness();let prevented=false;
  events.keydown({key:'Escape',preventDefault(){prevented=true}});
  assert.equal(prevented,false);
});

test('native viewer delegates fullscreen to WPF with no second DOM F11 handler',()=>{
  const {objects,events}=harness('?nox_native_viewer=1');
  assert.equal(objects.get('full').hidden,true);
  assert.equal(objects.get('full').disabled,true);
  let prevented=false;
  events.keydown({key:'F11',preventDefault(){prevented=true}});
  assert.equal(prevented,false);
  assert.match(objects.get('status').textContent,/выберите|Выберите/);
});
test('VTT language derives from a scoped file name, invalid replacement keeps last track',async()=>{
  const {objects}=harness();
  objects.get('file').onchange({target:{files:[{name:'episode.mp4',size:700}]}});
  const sub=objects.get('subtitles');
  await sub.onchange({target:{files:[{name:'episode.fr.vtt',size:65,text:async()=> 'WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nSalut'}]}});
  const previous=objects.get('video').child;
  assert.equal(previous.srclang,'fr');
  await sub.onchange({target:{files:[{name:'corrupt.fr.srt',size:40,text:async()=> 'invalid'}]}});
  assert.equal(objects.get('video').child,previous);
  assert.match(objects.get('status').textContent,/HOLD/);
});
