echo "C300: k8_s2"
# Флаги: K8_READER=1 включает подключение чтения вслух в читалке (по умолчанию выключено до отдельного подтверждения)
K8_READER=${K8_READER:-0}
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PATH=/workspace/nox/tools/node/bin:$PATH
if [ ! -f vendor/painterro/painterro.min.js ]; then rm -rf /tmp/k8pt; mkdir /tmp/k8pt; (cd /tmp/k8pt && timeout 100 npm pack painterro 2>&1 | tail -1; tar xzf *.tgz); mkdir -p vendor/painterro; cp /tmp/k8pt/package/build/painterro.min.js vendor/painterro/ 2>&1; cp /tmp/k8pt/package/LICENSE* vendor/painterro/ 2>/dev/null; ls -la vendor/painterro
echo "| painterro | $(grep -o '"version": *"[^"]*"' /tmp/k8pt/package/package.json | head -1 | cut -d'"' -f4) | MIT | vendor/painterro/painterro.min.js | <script src=\"./vendor/painterro/painterro.min.js\"></script> Painterro({}).show(dataURL) | студия дизайна (K8) | ok |" >> vendor/VENDOR_INDEX.md; fi
cp nox-k8-ui.css nox-k8-ui.css.bak_k8_$TS 2>/dev/null
grep -q "K8 студия, статусы" nox-k8-ui.css || cat >> nox-k8-ui.css <<'K8EOF'
/* K8 студия, статусы, эмоция */
:root{--k8-glow:transparent;--k8-idle:#8a8f98;--k8-loading:#6aa9ff;--k8-running:#e9b465;--k8-failed:#ff6b6b;--k8-blocked:#b58cff;--k8-done:#6fd49b}
body::after{content:"";position:fixed;inset:0;pointer-events:none;z-index:1;box-shadow:inset 0 0 120px 10px var(--k8-glow);transition:box-shadow 1.2s}
.k8-s{display:inline-flex;align-items:center;gap:6px;min-height:24px;font-size:12px}.k8-s::before{content:"";width:8px;height:8px;border-radius:50%;background:var(--c,var(--k8-idle))}
.k8-s.idle{--c:var(--k8-idle)}.k8-s.loading{--c:var(--k8-loading)}.k8-s.running{--c:var(--k8-running)}.k8-s.failed{--c:var(--k8-failed)}.k8-s.blocked{--c:var(--k8-blocked)}.k8-s.done{--c:var(--k8-done)}
#k8-live{position:fixed;top:0;left:50%;transform:translateX(-50%);z-index:46;max-width:min(560px,70vw);padding:0 12px;min-height:24px;background:rgba(20,15,15,.85);border:1px solid rgba(255,255,255,.15);border-top:0;border-radius:0 0 12px 12px;color:#efe6df;text-decoration:none;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:12px;display:flex;align-items:center}
#k8-stop{position:fixed;right:12px;bottom:150px;z-index:9100;min-width:44px;min-height:44px;border-radius:22px;border:1px solid #ff6b6b;background:rgba(120,20,20,.92);color:#fff;font-size:14px;padding:0 16px;cursor:pointer}
#k8-stop[hidden]{display:none}
#k8-studio{display:flex;height:calc(100vh - 150px);min-height:480px;gap:0;width:100%;box-sizing:border-box}
#k8-cv{overflow:auto;min-width:0;position:relative}
#k8-chat{display:flex;flex-direction:column;min-width:0;border-left:1px solid rgba(255,255,255,.15);background:rgba(20,15,15,.6);color:#efe6df}
#k8-studio .gutter{background:rgba(255,255,255,.12);cursor:col-resize;width:8px}
.k8c-h{display:flex;gap:8px;align-items:center;padding:8px;border-bottom:1px solid rgba(255,255,255,.12)}
.k8c-f{flex:1;overflow-y:auto;padding:8px;display:flex;flex-direction:column;gap:8px}
.k8c-m{padding:8px 10px;border-radius:12px;background:rgba(255,255,255,.07);font-size:14px;white-space:pre-wrap;word-break:break-word;border:1px solid transparent;cursor:pointer}
.k8c-m.me{background:rgba(233,180,101,.18);align-self:flex-end}.k8c-m.hl{border-color:#e9b465}
.k8c-m blockquote{margin:0 0 6px;padding-left:8px;border-left:3px solid #e9b465;font-size:12px;opacity:.8}
.k8c-m img{max-width:100%;border-radius:8px;display:block;margin:6px 0}
.k8c-a{display:flex;gap:6px;margin-top:6px;flex-wrap:wrap}
.k8c-i{display:flex;gap:6px;padding:8px;border-top:1px solid rgba(255,255,255,.12);flex-wrap:wrap}
.k8c-i textarea,.k8-ta{flex:1;min-width:140px;min-height:44px;border-radius:12px;border:1px solid rgba(255,255,255,.22);background:rgba(0,0,0,.35);color:#efe6df;font-size:14px;padding:8px;font-family:inherit;box-sizing:border-box;width:100%}
.k8-conf{height:6px;border-radius:3px;background:rgba(255,255,255,.12);margin:6px 0;overflow:hidden}.k8-conf i{display:block;height:100%;background:var(--k8-done)}
.k8-src{font-size:12px}.k8-src summary{min-height:44px;display:flex;align-items:center;cursor:pointer}
.k8-it{display:flex;gap:8px;align-items:flex-start;margin:6px 0;font-size:13px}.k8-it img{width:96px;height:96px;object-fit:cover;border-radius:8px}
img-comparison-slider{width:100%;max-width:420px;display:block;margin:6px 0}img-comparison-slider img{width:100%;display:block}
.k8-album{display:flex;gap:6px;flex-wrap:wrap}.k8-album img{width:64px;height:64px;object-fit:cover;border-radius:8px}
.k8-chips{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0}.k8-chips button{min-height:44px;padding:0 12px;border-radius:22px;border:1px solid rgba(255,255,255,.22);background:rgba(255,255,255,.07);color:#efe6df;font-size:13px;cursor:pointer}
@media(max-width:800px){#k8-studio{flex-direction:column;height:auto}#k8-cv,#k8-chat{width:100%!important;min-height:70vh}#k8-studio.tab-cv #k8-chat{display:none}#k8-studio.tab-chat #k8-cv{display:none}.k8c-tabs{display:flex!important}#k8-studio .gutter{display:none}}
.k8c-tabs{display:none;gap:8px;margin:0 0 8px}
K8EOF
cat > nox-k8-voice.js <<'K8EOF'
/* K8 №15: голосовой ввод (Web Speech), чтение вслух (speechSynthesis), мгновенный STOP. БЕЗ подмены window.fetch: запросы идут через K8voice.run(fn(signal)) с AbortController. API K8voice */
(function(){ if(window.K8voice)return;
 const ctls=new Set();let rec=null,speaking=false,btn,stopped=0;
 function upd(){ if(!btn){if(!document.body)return;btn=document.createElement('button');btn.type='button';btn.id='k8-stop';btn.textContent='STOP';btn.hidden=true;btn.addEventListener('click',stop);document.body.appendChild(btn)}btn.hidden=!(ctls.size||speaking||rec)}
 async function run(fn){const c=new AbortController();ctls.add(c);upd();const t=stopped;try{const r=await fn(c.signal);return t===stopped?r:null}catch(e){return null}finally{ctls.delete(c);upd()}}
 function stop(){stopped++;try{speechSynthesis.cancel()}catch(e){}speaking=false;try{rec&&rec.abort()}catch(e){}rec=null;ctls.forEach(function(c){try{c.abort()}catch(e){}});ctls.clear();fetch('/api/turn/stop',{method:'POST'}).catch(function(){});upd()}
 function say(t){ if(!('speechSynthesis' in window)||!t)return false;speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(String(t).slice(0,3000));u.lang='ru-RU';u.onend=u.onerror=function(){speaking=false;upd()};speaking=true;upd();speechSynthesis.speak(u);return true}
 function listen(cb){const R=window.SpeechRecognition||window.webkitSpeechRecognition;if(!R)return false;rec=new R();rec.lang='ru-RU';rec.interimResults=false;rec.onresult=function(e){cb(e.results[0][0].transcript)};rec.onend=rec.onerror=function(){rec=null;upd()};rec.start();upd();return true}
 document.addEventListener('keydown',function(e){if(e.key==='Escape'&&(ctls.size||speaking||rec))stop()});
 document.addEventListener('DOMContentLoaded',upd);
 window.K8voice={say:say,listen:listen,stop:stop,run:run,busy:function(){return ctls.size+(speaking?1:0)}};
})();
K8EOF
cat > nox-k8-meta.js <<'K8EOF'
/* K8 №14: эмоция meta.emo тонирует свечение; индикатор уверенности и «откуда я знаю» из meta.sources. БЕЗ подмены fetch: данные подаёт чат через K8meta.handle(json). API K8meta */
(function(){ if(window.K8meta)return;let last=null;
 const EMO=[[/рад|joy|happy|весел/i,'rgba(255,207,92,.35)'],[/груст|sad|печал/i,'rgba(106,169,255,.35)'],[/зл|anger|angry|гнев/i,'rgba(255,107,107,.35)'],[/страх|fear|тревог/i,'rgba(181,140,255,.35)'],[/интерес|curio|любоп/i,'rgba(111,212,155,.3)'],[/спокой|calm|нейтр/i,'rgba(255,255,255,.12)']];
 const K=function(s){return String(s).slice(0,120).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})};
 function emo(n){let c='transparent';EMO.some(function(e){if(e[0].test(String(n))){c=e[1];return true}});document.documentElement.style.setProperty('--k8-glow',c);return c}
 function render(el,m){m=m||{};const cf=m.confidence!=null?m.confidence:m.conf;let h='';
  if(cf!=null){const p=Math.round((cf>1?cf/100:cf)*100);h+='<div class="k8-conf" role="img" aria-label="Уверенность '+p+'%"><i style="width:'+p+'%"></i></div><div class="k8-st">Уверенность '+p+'%</div>'}
  const s=m.sources;if(Array.isArray(s)&&s.length){h+='<details class="k8-src"><summary>Откуда я это знаю</summary><ul>'+s.slice(0,8).map(function(x){const t=typeof x==='string'?x:(x.title||x.url||x.name||JSON.stringify(x));return'<li>'+K(t)+'</li>'}).join('')+'</ul></details>'}
  if(h){const d=document.createElement('div');d.innerHTML=h;el.appendChild(d)}return !!h}
 function handle(j){const m=j&&(j.meta||(j.result&&j.result.meta));if(!m)return null;last=m;if(m.emo)emo(m.emo);document.dispatchEvent(new CustomEvent('k8:meta',{detail:m}));return m}
 window.K8meta={emo:emo,render:render,last:function(){return last},handle:handle};
})();
K8EOF
cat > nox-k8-win.js <<'K8EOF'
/* K8 №17: конфетти со звуком на победах, не чаще раза в N минут. API K8win.fire(текст) */
(function(){ if(window.K8win)return;
 const LK='nox.k8.win.t',NK='nox.k8.win.min';let C=null;
 const mins=function(){return +localStorage.getItem(NK)||3};
 async function lib(){ if(C)return C;await new Promise(function(ok){const s=document.createElement('script');s.src='./vendor/canvas-confetti/canvas-confetti.iife.js';s.onload=ok;s.onerror=ok;document.head.appendChild(s)});
  const g=window.NOX_canvas_confetti||window.confetti;C=g&&(typeof g==='function'?g:(g.default||g.confetti));return C}
 function beep(){try{const a=new (window.AudioContext||window.webkitAudioContext)(),t=a.currentTime;[523,659,784].forEach(function(f,i){const o=a.createOscillator(),g=a.createGain();o.frequency.value=f;o.connect(g);g.connect(a.destination);g.gain.setValueAtTime(.06,t+i*.12);g.gain.exponentialRampToValueAtTime(.001,t+i*.12+.2);o.start(t+i*.12);o.stop(t+i*.12+.22)})}catch(e){}}
 async function fire(label,force){const now=Date.now(),last=+localStorage.getItem(LK)||0;if(!force&&now-last<mins()*60000)return false;localStorage.setItem(LK,String(now));
  const c=await lib();if(c)c({particleCount:140,spread:80,origin:{y:.7},zIndex:9500,disableForReducedMotion:true});beep();
  const t=document.createElement('div');t.setAttribute('role','status');t.style.cssText='position:fixed;left:50%;top:48px;transform:translateX(-50%);z-index:9500;padding:10px 18px;border-radius:14px;background:rgba(20,15,15,.92);color:#efe6df;border:1px solid #e9b465;font-size:14px';t.textContent=label||'Победа';document.body.appendChild(t);setTimeout(function(){t.remove()},2500);return true}
 let known=null;setInterval(function(){try{const j=JSON.parse(localStorage.getItem('nox.tasks.v1')||'{}');const dn=(j.tasks||[]).filter(function(t){return t.done||t.status==='done'||t.col==='done'}).length;if(known!=null&&dn>known)fire('Задача закрыта');known=dn}catch(e){}},5000);
 document.addEventListener('k8:win',function(e){fire(e.detail&&e.detail.label)});
 window.K8win={fire:fire,setMinutes:function(n){localStorage.setItem(NK,String(n))}};
})();
K8EOF
cat > nox-k8-live.js <<'K8EOF'
/* K8 №14: строка статуса обучения в шапке (data/live.json). API K8live */
(function(){ if(window.K8live)return;let el;
 async function tick(){try{const j=await fetch('./data/live.json',{cache:'no-store'}).then(function(r){return r.json()});const t=String(j.round||'').replace(/^\d{4}-\d\d-\d\dT[\d:]+Z\s*/,'').slice(0,100)||'нет данных';
  if(!el){el=document.createElement('a');el.id='k8-live';el.href='./training.html';el.setAttribute('aria-label','Статус обучения');document.body.appendChild(el)}
  const run=/ОБУЧ|train/i.test(t);el.innerHTML='<span class="k8-s '+(run?'running':'idle')+'">Обучение: '+t.replace(/[<>&]/g,'')+'</span>';return t}catch(e){return null}}
 document.addEventListener('DOMContentLoaded',function(){tick();setInterval(tick,60000)});
 window.K8live={tick:tick};
})();
K8EOF
cat > nox-k8-persona.js <<'K8EOF'
/* K8 №8: пульт характера в настройках (юмор, прямота, теплота, краткость) -> localStorage + /api/persona, подмешивается в промпт через обёртку K4.ask. API K8persona */
(function(){ if(window.K8persona)return;const PK='nox.k8.persona';
 const D={humor:60,directness:55,warmth:70,brevity:60},N={humor:'Юмор',directness:'Прямота',warmth:'Теплота',brevity:'Краткость'};
 function get(){try{return Object.assign({},D,JSON.parse(localStorage.getItem(PK)||'{}'))}catch(e){return Object.assign({},D)}}
 function hint(){const p=get();return'[Характер NOX 0-100: юмор '+p.humor+', прямота '+p.directness+', теплота '+p.warmth+', краткость '+p.brevity+'] '}
 function set(k,v){const p=get();p[k]=Math.max(0,Math.min(100,+v||0));localStorage.setItem(PK,JSON.stringify(p));fetch('/api/persona',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)}).catch(function(){});return p}
 function patch(){ if(window.K4&&K4.ask&&!K4.ask._k8){const o=K4.ask;K4.ask=function(pr,el){return o.call(K4,hint()+pr,el)};K4.ask._k8=1}}
 function panel(){const pg=document.getElementById('page');if(!pg||document.getElementById('k8-persona'))return;const s=document.createElement('section');s.id='k8-persona';s.className='k4-box';s.innerHTML='<h3>Пульт характера</h3><div class="k8-st">Значения подмешиваются в запросы NOX.</div>';const p=get();
  Object.keys(D).forEach(function(k){const w=document.createElement('div');w.innerHTML='<label class="k8-st" for="k8p-'+k+'">'+N[k]+'</label>';let r;
   if(customElements.get('sl-range')){r=document.createElement('sl-range');r.addEventListener('sl-input',function(){set(k,r.value)})}else{r=document.createElement('input');r.type='range';r.addEventListener('input',function(){set(k,r.value)})}
   r.id='k8p-'+k;r.min=0;r.max=100;r.step=5;r.value=p[k];r.style.cssText='width:100%;min-height:44px';w.appendChild(r);s.appendChild(w)});pg.appendChild(s)}
 if(window.K4)patch();else document.addEventListener('DOMContentLoaded',patch);
 document.addEventListener('DOMContentLoaded',panel);
 window.K8persona={get:get,set:set,hint:hint,panel:panel};
})();
K8EOF
cat > nox-k8-read.js <<'K8EOF'
/* K8 №15: «Читать вслух» в читалке (выключено флагом K8_READER=0 в k8_s2.sh). API K8read */
(function(){ if(window.K8read||!window.K4)return;
 function text(){const s=String(getSelection()||'').trim();if(s)return s;const m=document.querySelector('main,#page,article');return(m?m.innerText:document.body.innerText).slice(0,3000)}
 function go(){return window.K8voice?K8voice.say(text()):false}
 K4.fab('k8-read-b','Читать вслух','volume-2',go);
 window.K8read={go:go,text:text};
})();
K8EOF
cat > nox-studio.js <<'K8EOF'
/* NOX studio: общий шаблон. Полотно слева, чат справа (split.js ~380px), вкладки на мобильном. Применён к creative (#dz). API K8studio */
(function(){ if(window.K8studio||!window.K4)return;
 const page=document.getElementById('page');if(!page||!document.getElementById('dz'))return;
 const HK='nox.k8.chat.design';let hist=[],feed,inp,quote=null;
 try{hist=JSON.parse(localStorage.getItem(HK)||'[]')}catch(e){}
 const sh=document.createElement('div');sh.id='k8-studio';sh.className='tab-chat';
 const cv=document.createElement('div');cv.id='k8-cv';const ch=document.createElement('div');ch.id='k8-chat';
 while(page.firstChild)cv.appendChild(page.firstChild);
 ch.innerHTML='<div class="k8c-h"><sl-select id="k8c-role" size="small" value="design" style="flex:1"><sl-option value="design">Дизайнер</sl-option></sl-select><span class="k8-s idle" id="k8c-st">готов</span></div><div class="k8c-f" id="k8c-f" aria-live="polite"></div><div class="k8c-i"><textarea id="k8c-in" aria-label="Сообщение" placeholder="Сообщение или /рисуй описание"></textarea><button type="button" class="k4-btn pri" id="k8c-go">Отправить</button><button type="button" class="k4-btn" id="k8c-mic" aria-label="Голосовой ввод">Микрофон</button><label class="k4-btn" for="k8c-at" style="cursor:pointer">Вложить</label><input id="k8c-at" type="file" accept="image/*" hidden></div>';
 const tabs=document.createElement('div');tabs.className='k8c-tabs';tabs.innerHTML='<button type="button" class="k4-btn" data-t="cv">Полотно</button><button type="button" class="k4-btn" data-t="chat">Чат</button>';
 sh.appendChild(cv);sh.appendChild(ch);page.appendChild(tabs);page.appendChild(sh);
 tabs.addEventListener('click',function(e){const t=e.target.dataset&&e.target.dataset.t;if(t)sh.className='tab-'+t});
 feed=ch.querySelector('#k8c-f');inp=ch.querySelector('#k8c-in');
 K4.load('./vendor/split.js/split.min.js').then(function(){ if(window.Split&&innerWidth>800){const p=Math.min(40,Math.max(20,380/innerWidth*100));window.Split([cv,ch],{sizes:[100-p,p],minSize:[320,300],gutterSize:8})}});
 function save(){localStorage.setItem(HK,JSON.stringify(hist.slice(-200)))}
 function setSt(c,t){const s=ch.querySelector('#k8c-st');s.className='k8-s '+c;s.textContent=t}
 function render(m,i){const d=document.createElement('div');d.className='k8c-m'+(m.me?' me':'');d.dataset.i=i;if(m.sel)d.dataset.sel=m.sel;
  if(m.q){const b=document.createElement('blockquote');b.textContent=m.q;d.appendChild(b)}
  const p=document.createElement('div');p.textContent=m.t||'';d.appendChild(p);
  if(m.img){const im=document.createElement('img');im.src=m.img;im.alt='Вложение';d.appendChild(im)}
  const a=document.createElement('div');a.className='k8c-a';a.innerHTML='<button type="button" class="k4-btn" data-a="re">Ответить</button><button type="button" class="k4-btn" data-a="say">Озвучить</button>';d.appendChild(a);
  if(!m.me&&m.meta&&window.K8meta)K8meta.render(d,m.meta);
  d.addEventListener('click',function(e){const b=e.target.closest&&e.target.closest('button[data-a]');
   if(b){if(b.dataset.a==='re'){quote=(m.t||'').slice(0,120);inp.placeholder='Ответ на: '+quote;inp.focus()}else if(window.K8voice)K8voice.say(m.t||'');return}
   d.classList.add('hl');setTimeout(function(){d.classList.remove('hl')},1500);if(m.sel)hl(m.sel)});
  feed.appendChild(d);feed.scrollTop=feed.scrollHeight;return d}
 function hl(sel){try{const e=document.querySelector(sel);if(e){const o=e.style.outline;e.style.outline='3px solid #e9b465';e.scrollIntoView({block:'nearest'});setTimeout(function(){e.style.outline=o},1800)}}catch(x){}}
 function post(m){hist.push(m);save();return render(m,hist.length-1)}
 hist.forEach(render);
 async function send(text,img){text=(text||inp.value).trim();if(!text&&!img)return;const m={me:1,t:text,ts:Date.now()};if(quote)m.q=quote;if(img)m.img=img;post(m);inp.value='';inp.placeholder='Сообщение или /рисуй описание';const q=quote;quote=null;
  const V=window.K8voice,wrap=V?V.run:function(f){return f()};
  if(/^\/рисуй\s+/i.test(text)&&window.K8draw){setSt('running','рисую');await wrap(function(sig){return K8draw.run(text.replace(/^\/рисуй\s+/i,''),3,sig)});setSt('done','готово');return}
  setSt('running','думаю');const box=document.createElement('div');box.className='k8c-m';box.textContent='…';feed.appendChild(box);
  const ok=await wrap(async function(){await K4.ask('Ты дизайнер NOX, отвечай коротко. '+(q?'Контекст: '+q+'. ':'')+text,box);return 1});
  if(ok){post({t:box.textContent,ts:Date.now(),meta:window.K8meta&&K8meta.last()})}else{setSt('blocked','остановлено')}box.remove();if(ok)setSt('idle','готов')}
 ch.querySelector('#k8c-go').addEventListener('click',function(){send()});
 inp.addEventListener('keydown',function(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send()}});
 ch.querySelector('#k8c-mic').addEventListener('click',function(){window.K8voice?K8voice.listen(function(t){inp.value=(inp.value+' '+t).trim()}):0});
 ch.querySelector('#k8c-at').addEventListener('change',function(e){const f=e.target.files[0];if(!f)return;const r=new FileReader();r.onload=function(){send('Вложение: '+f.name,r.result)};r.readAsDataURL(f)});
 window.K8studio={post:post,send:send,hl:hl,setSt:setSt,feed:function(){return feed},hist:function(){return hist}};
})();
K8EOF
cat > nox-k8-draw.js <<'K8EOF'
/* K8 №7: рисование с самооценкой, позитив/негатив отдельно, выбор пользователя = датасет вкуса, «до/после», Painterro. API K8draw */
(function(){ if(window.K8draw||!window.K4)return;
 const TK='nox.k8.taste',NK='nox.k8.neg';
 const PRE=['размытие','лишние пальцы','искажённые руки','водяной знак','текст на изображении','низкое качество','пересвет','пластиковая кожа','плохая анатомия','артефакты сжатия'];
 const taste=function(){try{return JSON.parse(localStorage.getItem(TK)||'[]')}catch(e){return[]}};
 const negS=function(){try{return Object.assign({on:false,auto:false,text:''},JSON.parse(localStorage.getItem(NK)||'{}'))}catch(e){return{on:false,auto:false,text:''}}};
 const negSave=function(s){localStorage.setItem(NK,JSON.stringify(s))};
 function findImg(j,dep){dep=dep||0;if(dep>5||j==null)return null;if(typeof j==='string'){if(/^data:image/.test(j))return j;if(/^(https?:)?\/\/|^\/[\w./-]+\.(png|jpe?g|webp)/i.test(j)&&/\.(png|jpe?g|webp)(\?|$)/i.test(j))return j;if(j.length>2000&&/^[A-Za-z0-9+/=\s]+$/.test(j.slice(0,200)))return'data:image/png;base64,'+j.replace(/\s/g,'');return null}
  if(Array.isArray(j)){for(const x of j){const r=findImg(x,dep+1);if(r)return r}return null}
  if(typeof j==='object'){for(const k of Object.keys(j)){const r=findImg(j[k],dep+1);if(r)return r}}return null}
 async function gen(prompt,sig){const n=negS(),body={prompt:prompt,width:512,height:512,steps:8};if(n.on&&n.text.trim())body.negative_prompt=n.text.trim();
  const r=await fetch('/img/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:sig});const j=await r.json().catch(function(){return null});
  let u=findImg(j);if(u)return u;const id=j&&(j.job_id||j.id);
  for(let i=0;id&&i<60&&!u;i++){await new Promise(function(o){setTimeout(o,2000)});const jr=await fetch('/api/creative/job/'+id,{signal:sig}).then(function(x){return x.json()}).catch(function(){return null});u=findImg(jr)}
  return u}
 async function durl(u){if(/^data:/.test(u))return u;const b=await fetch(u).then(function(r){return r.blob()});return new Promise(function(ok){const f=new FileReader();f.onload=function(){ok(f.result)};f.readAsDataURL(b)})}
 async function critique(u,prompt,sig){try{const img=await durl(u);const r=await fetch('/vision/describe',{method:'POST',headers:{'Content-Type':'application/json'},signal:sig,body:JSON.stringify({image:img,prompt:'Оцени рисунок по запросу «'+prompt+'». Ответ строго: ОЦЕНКА: N/10. ОШИБКИ: через запятую.'})});const j=await r.json();
   const t=typeof j==='string'?j:(j.text||j.description||j.answer||j.result||JSON.stringify(j));const m=/(\d+(?:[.,]\d+)?)\s*\/\s*10/.exec(t);const e=/ОШИБК[ИА]:?\s*([^\n]*)/i.exec(t);
   return{score:m?Math.min(10,parseFloat(m[1].replace(',','.'))):null,errors:e?e[1].trim().slice(0,200):'',text:String(t).slice(0,300)}}catch(e){return{score:null,errors:'',text:'Зрение недоступно'}}}
 async function run(prompt,n,sig){n=Math.max(1,Math.min(3,n||3));const its=[];let p=prompt,S=window.K8studio;
  for(let i=0;i<n;i++){S&&S.setSt('running','итерация '+(i+1)+'/'+n);const u=await gen(p,sig).catch(function(){return null});if(!u){S&&S.post({t:'Итерация '+(i+1)+': картинка не получена',ts:Date.now()});break}
   const c=await critique(u,prompt,sig);its.push({u:u,score:c.score,errors:c.errors,p:p});
   S&&S.post({t:'Итерация '+(i+1)+(c.score!=null?' · оценка '+c.score+'/10':'')+(c.errors?'\nОшибки: '+c.errors:'')+(c.score==null?'\n'+c.text:''),img:u,ts:Date.now(),sel:'#dz'});
   if(c.score!=null&&c.score>=8.5)break;if(c.errors)p=prompt+'. Исправить: '+c.errors}
  if(its.length)choose(prompt,its);return its}
 function choose(prompt,its){const S=window.K8studio;const d=document.createElement('div');d.className='k8c-m';d.innerHTML='<div>Выберите лучший вариант:</div>';
  its.forEach(function(it,i){const row=document.createElement('div');row.className='k8-it';row.innerHTML='<img alt="Итерация '+(i+1)+'"><div>'+(it.score!=null?it.score+'/10':'без оценки')+'<div class="k8c-a"><button type="button" class="k4-btn">Выбрать</button><button type="button" class="k4-btn">Редактор</button></div></div>';row.querySelector('img').src=it.u;
   const b=row.querySelectorAll('button');b[0].addEventListener('click',function(){pick(prompt,its,i);d.remove()});b[1].addEventListener('click',function(){edit(it.u,function(n){it.u=n;row.querySelector('img').src=n})});d.appendChild(row)});
  if(its.length>1){const cmp=document.createElement('div');cmp.id='k8-cmp';d.appendChild(cmp);K4.load('./vendor/img-comparison-slider/img-comparison-slider.iife.js').then(function(){cmp.innerHTML='<img-comparison-slider><img slot="first" alt="Первая версия"><img slot="second" alt="Последняя версия"></img-comparison-slider>';const im=cmp.querySelectorAll('img');im[0].src=its[0].u;im[1].src=its[its.length-1].u})}
  S&&S.feed().appendChild(d);S&&(S.feed().scrollTop=S.feed().scrollHeight)}
 function pick(prompt,its,i){const t=taste();t.push({prompt:prompt,negative:negS().on?negS().text:'',chosen:its[i].u.slice(0,200000),score:its[i].score,rejected:its.filter(function(_,k){return k!==i}).map(function(x){return{score:x.score,errors:x.errors}}),ts:Date.now()});
  try{localStorage.setItem(TK,JSON.stringify(t.slice(-60)))}catch(e){}if(window.K8win)K8win.fire('Выбор сохранён');if(window.K8studio)K8studio.post({t:'Выбор сохранён в «мой стиль растёт» ('+t.length+')',ts:Date.now()})}
 async function edit(u,cb){await K4.load('./vendor/painterro/painterro.min.js');if(!window.Painterro)return false;const P=window.Painterro({saveHandler:function(img,done){cb&&cb(img.asDataURL());done(true)}});P.show(u);return true}
 function album(el){const t=taste();el.innerHTML='<div class="k8-st">Мой стиль растёт: '+t.length+' выборов</div><div class="k8-album"></div>';const a=el.querySelector('.k8-album');t.slice(-12).forEach(function(x){const i=document.createElement('img');i.src=x.chosen;i.alt=x.prompt.slice(0,40);a.appendChild(i)})}
 async function autoNeg(pos,el){const box=document.createElement('div');await K4.ask('Составь негативный промпт (через запятую, без пояснений) для рисунка: '+pos,box);return box.textContent.replace(/^…$/,'').trim()}
 function promptPanel(d){const s=negS();d.innerHTML='<label class="k8-st" for="k8-pos">Позитив</label><textarea id="k8-pos" class="k8-ta" placeholder="Что нарисовать"></textarea>'+
  '<div class="k8-row"><sl-switch id="k8-nsw">Негатив</sl-switch></div><div id="k8-nbox"><div class="k8-row"><sl-switch id="k8-nau">Авто</sl-switch></div><label class="k8-st" for="k8-neg">Негатив</label><textarea id="k8-neg" class="k8-ta" placeholder="Чего не должно быть"></textarea><div class="k8-chips" id="k8-chips"></div></div>'+
  '<div class="k8-row"><button type="button" class="k4-btn pri" id="k8-go">Нарисовать</button></div>';
  const sw=d.querySelector('#k8-nsw'),au=d.querySelector('#k8-nau'),nb=d.querySelector('#k8-nbox'),ng=d.querySelector('#k8-neg'),pos=d.querySelector('#k8-pos');
  sw.checked=!!s.on;au.checked=!!s.auto;ng.value=s.text;nb.hidden=!s.on;
  const save=function(){negSave({on:!!sw.checked,auto:!!au.checked,text:ng.value})};
  sw.addEventListener('sl-change',function(){nb.hidden=!sw.checked;save()});au.addEventListener('sl-change',save);ng.addEventListener('input',save);
  PRE.forEach(function(p){const b=document.createElement('button');b.type='button';b.textContent='+ '+p;b.addEventListener('click',function(){ng.value=(ng.value?ng.value+', ':'')+p;save()});d.querySelector('#k8-chips').appendChild(b)});
  d.querySelector('#k8-go').addEventListener('click',async function(){const t=pos.value.trim();if(!t)return;if(au.checked&&sw.checked){ng.value=await autoNeg(t)||ng.value;save()}
   if(window.K8studio)K8studio.send('/рисуй '+t);else run(t,3)});return d}
 K4.fab('k8-prompt-b','Позитив и негатив','pencil',function(){const d=K4.modal('k8-prompt-d','Промпт рисунка');if(!d.querySelector('#k8-pos'))promptPanel(d);d.show()});
 K4.fab('k8-album-b','Мой стиль','palette',function(){const d=K4.modal('k8-album-d','Мой стиль растёт');d.innerHTML='<div id="k8-alb"></div>';album(d.querySelector('#k8-alb'));d.show()});
 window.K8draw={run:run,gen:gen,critique:critique,taste:taste,album:album,edit:edit,findImg:findImg,pick:pick,neg:negS,presets:PRE};
})();
K8EOF
add(){ f=$1.html; [ -f $f ] || { echo "no $f"; return; }
 grep -q "nox-k8-$2.js\|nox-$2.js" $f && { echo "have $f $2"; return; }
 [ -f $f.bak_k8_$TS ] || cp $f $f.bak_k8_$TS; tag=""
 grep -q "nox-k4-core.js" $f || tag="<script src=\"./nox-k4-core.js?v=k4a\" defer></script>"
 grep -q "nox-k8-ui.css" $f || tag="$tag<link rel=\"stylesheet\" href=\"./nox-k8-ui.css?v=k8b\">"
 case $2 in studio) src="nox-studio.js";; *) src="nox-k8-$2.js";; esac
 tag="$tag<script src=\"./$src?v=k8b\" defer></script>"
 python3 - "$f" "$tag" <<'PYX'
import sys
f,t=sys.argv[1],sys.argv[2]
s=open(f,encoding='utf-8').read();i=s.rfind('</body>')
open(f,'w',encoding='utf-8').write(s[:i]+t+s[i:] if i>=0 else s+t)
PYX
 echo "added $2 -> $f"; }
for m in meta voice win live draw studio; do add creative $m; done
add settings persona; add settings live; add settings meta; add settings voice
add index win; add index voice; add index meta; add index live
if [ "$K8_READER" = 1 ]; then for r in book-reader library reader; do [ -f $r.html ] && { add $r voice; add $r read; echo "reader=$r"; break; }; done; else echo "reader: флаг K8_READER=0, читалка не тронута"; fi
echo "K8: студия дизайна (шаблон nox-studio.js), позитив/негатив, рисование с самооценкой, Painterro, до/после, конфетти, голос+STOP, статус обучения" >> qa/rework/creative.fixed
echo "K8: пульт характера (persona) + статус обучения" >> qa/rework/settings.fixed
echo "K8: конфетти, голос+STOP, статус обучения" >> qa/rework/index.fixed
echo "K8: пакет S2. Без подмены fetch. Читалка: флаг K8_READER (по умолчанию 0). Не сделано: шкала голода, лента «чему я научился» (ждёт данные P2), реестр ролей/Писатель, Ghost-Tab в новых полях. Бэкапы *.bak_k8_$TS." >> K8_LOG.md
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
curl -s -m 5 -o /dev/null -w "http %{http_code}\n" http://127.0.0.1:8091/web/index.html
timeout 200 $PY - <<'QAEOF' | tee /tmp/k8_qa_s2.txt
import asyncio
from playwright.async_api import async_playwright
JS={'creative':("K8studio","""(async()=>{const o={};o.studio=!!document.getElementById('k8-studio');o.dz=!!document.querySelector('#k8-cv #dz');o.chat=!!document.getElementById('k8-chat');K8studio.post({me:1,t:'тест'});o.hist=K8studio.hist().length;const hs=[...document.querySelectorAll('#k8-chat button')].filter(x=>x.offsetParent).map(x=>x.getBoundingClientRect().height);o.minbtn=Math.min(...hs);o.cw=Math.round(document.getElementById('k8-chat').getBoundingClientRect().width);K8meta.handle({meta:{emo:'радость',confidence:.8,sources:['а','б']}});o.glow=getComputedStyle(document.documentElement).getPropertyValue('--k8-glow');o.neg=K8draw.presets.length;o.fetchPatched=window.fetch.toString().indexOf('[native code]')>0;return JSON.stringify(o)})()"""),
 'settings':("K8persona","""(async()=>{K8persona.panel();K8persona.set('humor',90);return JSON.stringify({p:K8persona.get(),panel:!!document.getElementById('k8-persona'),ranges:document.querySelectorAll('#k8-persona [id^=k8p-]').length})})()"""),
 'index':("K8win","""(async()=>{const o={};localStorage.removeItem('nox.k8.win.t');o.f1=await K8win.fire('тест');o.f2=await K8win.fire('тест2');o.live=await K8live.tick();o.stop=!!K8voice;return JSON.stringify(o)})()""")}
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch(args=[])
    for w,h in((1440,900),(390,844)):
      for pg_ in ('creative','settings','index'):
        if pg_=='index' and w==390: continue
        pg=await b.new_page(viewport={'width':w,'height':h});errs=[];pg.on('pageerror',lambda e:errs.append(str(e)[:140]))
        try:
          await pg.goto('http://127.0.0.1:8091/web/%s.html'%pg_,wait_until='domcontentloaded',timeout=40000);await pg.wait_for_function('window.%s'%JS[pg_][0],timeout=15000);await pg.wait_for_timeout(1500)
          r=await asyncio.wait_for(pg.evaluate(JS[pg_][1]),40);print('QA',w,pg_,r,'errs',errs[:3])
        except Exception as e: print('QA EXC',w,pg_,str(e)[:200],errs[:3])
        await pg.close()
    await b.close()
asyncio.run(m())
QAEOF
if grep -q "CONNECTION_REFUSED" /tmp/k8_qa_s2.txt; then echo "QA пропущен (сайт лежит), файлы на диске"; else
 for pg in creative settings index; do if grep "QA.* $pg " /tmp/k8_qa_s2.txt | grep -q "EXC\|errs \['"; then b=$(ls $pg.html.bak_k8_$TS 2>/dev/null | head -1); [ -n "$b" ] && cp $b $pg.html && echo "ROLLBACK $pg from $b"; fi; done; fi
echo "K8 s2 done"
