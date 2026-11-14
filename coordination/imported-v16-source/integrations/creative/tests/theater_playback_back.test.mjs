import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const js = readFileSync(new URL('../web/theater.js', import.meta.url), 'utf8');
const html = readFileSync(new URL('../web/theater.html', import.meta.url), 'utf8');
function harness(query='?project=demo_1') {
  const items = new Map(), events = {}, revoked = [], created = [], navigated = [];
  let channel, counter = 0, pendingPlay = null;
  const create = id => {
    const el = { id, style:{}, textContent:'', files:[], src:'', events:{}, children:[],
      playCount:0, pauseCount:0, currentSrc:'',
      addEventListener(type, fn) { this.events[type] = fn; },
      removeEventListener(type, fn) { if(this.events[type]===fn) delete this.events[type]; },
      removeAttribute(attr) { if(attr==='src')this.src=''; },
      appendChild(child) { this.children.push(child); },
      load() { this.loaded=true; },
      pause() { this.pauseCount++; },
      play() { this.playCount++; return pendingPlay ?? Promise.resolve(); },
      requestFullscreen() { document.fullscreenElement=this; return Promise.resolve(); }
    };
    items.set(id,el);return el;
  };
  for(const id of ['video','poster','stage','status','title','space','file','subtitles','play','pause','back','full','screens']) create(id);
  const document = {
    getElementById:id => items.get(id), documentElement:{lang:'ru'}, fullscreenElement:null,
    exitFullscreen() { this.fullscreenElement=null;return Promise.resolve(); },
    createElement:() => ({ track:{mode:'disabled'},remove(){this.removed=true},addEventListener(){} })
  };
  const URL = {
    createObjectURL(obj) { created.push(obj);return 'blob:nox'+(++counter); },
    revokeObjectURL(uri) { revoked.push(uri); }
  };
  class BroadcastChannel {
    constructor(name) { this.name=name;channel=this; }
    close() { this.closed=true; }
  }
  const window = {
    location:{ search:query, assign(href) { navigated.push(href); } },
    addEventListener(type, fn) { events[type]=fn; }
  };
  vm.runInNewContext(js,{document,window,URL,URLSearchParams,Blob,Promise,Error,BroadcastChannel},{filename:'theater.js'});
  return { items, events, document, window, channel, revoked, created, navigated,
    setPendingPlay(p) { pendingPlay=p; },
    choose(name='film.mp4') { items.get('file').onchange({target:{files:[{name,size:120}],value:'C:\\mock'}}); },
    get status() { return items.get('status').textContent; },
    get video() { return items.get('video'); }
  };
}

const settle=async()=>{ await Promise.resolve();await Promise.resolve(); };
test('the same original cinema DOM gains only a local Back button',()=>{
  assert.match(html,/id="back"[^>]*aria-label="Вернуться в творческую студию"/);
  assert.match(html,/id="file"[^>]*type="file"/);
  assert.match(html,/id="subtitles"[^>]*type="file"/);
  assert.doesNotMatch(html,/<script[^>]+(?:http|\/\/)/i);
  assert.match(html,/prefers-reduced-motion/);
});
test('local MP4/WebM selection loads metadata, NEVER auto-plays',()=>{
  const h=harness(); h.choose('clip.webm');
  assert.equal(h.video.src,'blob:nox1');
  assert.equal(h.video.playCount,0);
  assert.match(h.status,/нажмите ▶/);
});
test('late successful play after Pause must not overwrite pause status',async()=>{
  const h=harness();h.choose();
  let resolve;h.setPendingPlay(new Promise(r=>{resolve=r;}));
  h.items.get('play').onclick();h.items.get('pause').onclick();
  resolve();await settle();
  assert.equal(h.status,'Пауза');
  assert.ok(h.video.pauseCount>=2);
});
test('late successful play from old file cannot override newer file selected',async()=>{
  const h=harness();h.choose('old.mp4');
  let resolve;h.setPendingPlay(new Promise(r=>{resolve=r;}));
  h.items.get('play').onclick();h.choose('new.webm');
  resolve();await settle();
  assert.match(h.status,/new.webm/);
  assert.deepEqual(h.revoked,['blob:nox1']);
});
test('late rejected play from corrupted film cannot overwrite decoder HOLD',async()=>{
  const h=harness();h.choose();
  let reject;h.setPendingPlay(new Promise((_,r)=>{reject=r;}));
  h.items.get('play').onclick();h.video.events.error();
  reject(new Error('decoder failed'));await settle();
  assert.match(h.status,/повреждено|формат не поддерживается/);
});
test('BroadcastChannel cannot start user-picked video without user activation',()=>{
  const h=harness();h.choose();
  h.channel.onmessage({data:{action:'play'}});
  assert.equal(h.video.playCount,0);
  assert.match(h.status,/MEDIA_HOLD/);
});
test('Back pauses and revokes local media, uses existing same-origin studio route',()=>{
  const h=harness('?nox_native_viewer=1');h.choose();
  h.items.get('back').onclick();
  assert.deepEqual(h.navigated,['studio.html']);
  assert.deepEqual(h.revoked,['blob:nox1']);
  assert.equal(h.channel.closed,true);
  assert.ok(h.video.pauseCount>=2);
  assert.equal(h.items.get('full').hidden,true);
});
test('Back cannot navigate away during browser DOM fullscreen',()=>{
  const h=harness();h.choose();
  h.document.fullscreenElement=h.items.get('stage');
  h.items.get('back').onclick();
  assert.deepEqual(h.navigated,[]);
  assert.match(h.status,/выйдите из полноэкранного режима/);
});
test('pagehide releases local media without claiming native playback',()=>{
  const h=harness();h.choose();
  h.events.pagehide();
  assert.deepEqual(h.revoked,['blob:nox1']);
  assert.equal(h.channel.closed,true);
});

test('BroadcastChannel cannot remotely start a native mapped project, manual Play remains working',async()=>{
  const h=harness('?project=demo_1&local_project_media=1');
  assert.match(h.video.src,/nox-projects\.invalid\/demo_1\/NOX_MOVIE_FINAL\.mp4/);
  h.channel.onmessage({data:{action:'play'}});
  assert.equal(h.video.playCount,0,'cross-context message is not a user gesture');
  assert.match(h.status,/MEDIA_HOLD/);
  h.items.get('play').onclick();await settle();
  assert.equal(h.video.playCount,1,'user can still play manually in existing WebView2');
  assert.equal(h.status,'Воспроизведение');
});
