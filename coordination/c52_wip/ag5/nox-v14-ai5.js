/* NOX HELION v14 · AI5: B17 повтор вдумчиво/быстро, B23 голосовой ввод, B24 озвучка ответа */
(()=>{'use strict';
if(window.NOX_V14_AI5)return;window.NOX_V14_AI5=1;
const D=document,W=window,MODE_KEY='nox.v14.mode';
const toast=(m,t)=>{try{W.NoxToast&&(W.NoxToast.show?W.NoxToast.show(m,t):typeof W.NoxToast==='function'&&W.NoxToast(m,t));}catch{}};
const msgs=()=>D.getElementById('messages');
const lastNox=()=>{const l=msgs()?.querySelectorAll('.msg.nox');return l&&l.length?l[l.length-1]:null;};
const bodyText=el=>{if(!el)return'';const c=el.querySelector(':scope>div')||el;const k=c.cloneNode(true);k.querySelectorAll('button,.nx-act-row,label,.nx-ai5-hover').forEach(n=>n.remove());return(k.textContent||'').trim();};
const lastUser=()=>{const l=msgs()?.querySelectorAll('.msg.me,.msg.user');return l&&l.length?bodyText(l[l.length-1]):'';};

/* ---------- поле ввода (textarea или loquix) ---------- */
function promptHost(){
  const c=D.querySelector('loquix-chat-composer');const pi=c?.shadowRoot?.querySelector('loquix-prompt-input');
  if(pi)return{kind:'loquix',composer:c,pi,area:pi.shadowRoot?.querySelector('textarea')};
  const a=D.getElementById('prompt');return a?{kind:'plain',area:a}:null;
}
function setPrompt(v){const h=promptHost();if(!h)return;
  if(h.kind==='loquix'){h.pi.value=v;if(h.area)h.area.value=v;h.pi.dispatchEvent(new CustomEvent('loquix-change',{bubbles:true,composed:true,detail:{value:v}}));}
  else{h.area.value=v;h.area.dispatchEvent(new Event('input',{bubbles:true}));}}
function getPrompt(){const h=promptHost();return h?(h.kind==='loquix'?(h.pi.value||h.area?.value||''):h.area.value):'';}
function submitPrompt(text){const h=promptHost();
  if(h?.kind==='loquix'){h.composer.dispatchEvent(new CustomEvent('loquix-submit',{bubbles:true,composed:true,detail:{content:text}}));return true;}
  const f=D.getElementById('chatForm');if(!f)return false;setPrompt(text);
  if(f.requestSubmit)f.requestSubmit();else f.dispatchEvent(new Event('submit',{cancelable:true,bubbles:true}));return true;}

/* ---------- B17: одноразовая обёртка fetch с options.mode ---------- */
let busy=false;
function isChatPost(input,init){let p='';try{p=new URL(typeof input==='string'?input:(input&&input.url)||'',location.href).pathname;}catch{}
  const m=String(init?.method||(input&&input.method)||'GET').toUpperCase();return m==='POST'&&(p==='/api/chat'||p==='/api/nox/chat/stream');}
function armMode(mode){
  const prevLS=(()=>{try{return localStorage.getItem(MODE_KEY);}catch{return null;}})();
  try{localStorage.setItem(MODE_KEY,mode);}catch{}
  const prev=W.fetch;let done=false,timer;
  const restoreLS=()=>{try{prevLS===null?localStorage.removeItem(MODE_KEY):localStorage.setItem(MODE_KEY,prevLS);}catch{}};
  const unwrap=()=>{done=true;clearTimeout(timer);if(W.fetch===wrapped)W.fetch=prev;setTimeout(restoreLS,0);};
  const wrapped=function(input,init){
    if(!done&&isChatPost(input,init)&&init&&typeof init.body==='string'){
      try{const b=JSON.parse(init.body);b.options=Object.assign({},b.options||{},{mode});init=Object.assign({},init,{body:JSON.stringify(b)});W.NoxAI5.lastMode=mode;}catch{}
      unwrap();
    }
    return prev.apply(this,[input,init]);
  };
  W.fetch=wrapped;timer=setTimeout(unwrap,15000);
}
function retry(mode){
  if(busy)return;const q=lastUser();
  if(!q){toast('Нет вопроса для повтора','warn');return;}
  armMode(mode);
  if(!submitPrompt(q)){toast('Отправка недоступна','warn');return;}
  toast(mode==='deep'?'Повтор · вдумчиво':'Повтор · быстро','info');
}

/* ---------- B24: озвучка ---------- */
const TTS='speechSynthesis' in W&&typeof W.SpeechSynthesisUtterance==='function';
let speaking=null;
function plain(t){return String(t||'')
  .replace(/```[\s\S]*?```/g,' ').replace(/`([^`]*)`/g,'$1')
  .replace(/!\[([^\]]*)\]\([^)]*\)/g,'$1').replace(/\[([^\]]+)\]\([^)]*\)/g,'$1')
  .replace(/^\s{0,3}#{1,6}\s+/gm,'').replace(/^\s*>\s?/gm,'').replace(/^\s*[-*+]\s+/gm,'').replace(/^\s*\d+[.)]\s+/gm,'')
  .replace(/(\*\*|__|~~)(.*?)\1/g,'$2').replace(/[*_~#|>`]/g,' ').replace(/\s+/g,' ').trim();}
function ruVoice(){try{const v=speechSynthesis.getVoices()||[];return v.find(x=>/^ru(-|_|$)/i.test(x.lang))||null;}catch{return null;}}
function stopSpeak(){try{speechSynthesis.cancel();}catch{}speaking=null;syncSay();}
function speak(msg){
  if(!TTS)return;if(speaking===msg){stopSpeak();return;}
  try{speechSynthesis.cancel();}catch{}
  const txt=plain(bodyText(msg));if(!txt){toast('Нечего озвучивать','warn');return;}
  const u=new SpeechSynthesisUtterance(txt.slice(0,30000));u.lang='ru-RU';const v=ruVoice();if(v)u.voice=v;
  u.onend=u.onerror=()=>{if(speaking===msg){speaking=null;syncSay();}};
  speaking=msg;syncSay();try{speechSynthesis.speak(u);}catch{speaking=null;syncSay();}
}
function syncSay(){D.querySelectorAll('[data-act="ai5-say"],.nx-ai5-hover').forEach(b=>{const m=b.closest('.msg.nox');const on=!!m&&m===speaking;
  if(b.classList.contains('is-on')===on&&b.hasAttribute('aria-pressed'))return;
  b.classList.toggle('is-on',on);b.setAttribute('aria-pressed',String(on));
  const l=on?'Остановить озвучку':'Озвучить ответ';b.setAttribute('aria-label',l);b.title=l;});}
/* ---------- ряд действий ---------- */
const SVG=(d,c)=>`<svg class="${c||''}" viewBox="0 0 24 24" aria-hidden="true"><path d="${d}" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const ICON={'ai5-deep':SVG('M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7'),'ai5-fast':SVG('M13 2 4 14h7l-1 8 9-12h-7z'),
  'ai5-say':SVG('M4 9v6h4l5 4V5L8 9zM16 9a4 4 0 0 1 0 6M18.5 6.5a8 8 0 0 1 0 11','nx-i-say')+SVG('M7 7h10v10H7z','nx-i-stop')};
function chip(act,label,title){const b=D.createElement('button');b.type='button';b.className='nx-chip nx-ai5-chip';b.dataset.act=act;b.innerHTML=ICON[act]+(label?`<span>${label}</span>`:'');b.title=title;b.setAttribute('aria-label',title);return b;}
function ensureRow(){
  const m=lastNox();
  D.querySelectorAll('.nx-act-row [data-act^="ai5-"]').forEach(b=>{if(b.closest('.msg.nox')!==m)b.remove();});
  if(m&&TTS)D.querySelectorAll('.msg.nox').forEach(x=>{if(!x.querySelector(':scope>.nx-ai5-hover')){const h=D.createElement('button');h.type='button';h.className='nx-ai5-hover';h.innerHTML=ICON['ai5-say'];h.setAttribute('aria-label','Озвучить ответ');h.title='Озвучить ответ';x.append(h);}});
  if(!m)return;
  let row=m.querySelector('.nx-act-row');
  if(!row){row=D.createElement('div');row.className='nx-act-row';row.setAttribute('role','toolbar');row.setAttribute('aria-label','Действия с ответом');m.append(row);}
  const add=(a,l,t)=>{if(!row.querySelector(`[data-act="${a}"]`))row.append(chip(a,l,t));};
  add('ai5-deep','Ещё раз: вдумчиво','Повторить последний вопрос в режиме deep');
  add('ai5-fast','Ещё раз: быстро','Повторить последний вопрос в режиме fast');
  if(TTS)add('ai5-say','','Озвучить ответ');
  row.querySelectorAll('[data-act="ai5-deep"],[data-act="ai5-fast"]').forEach(b=>{if(b.disabled!==busy)b.disabled=busy;});
  syncSay();
}
let t=0;const schedule=()=>{clearTimeout(t);t=setTimeout(ensureRow,120);};
D.addEventListener('click',e=>{
  const b=e.target.closest?.('[data-act^="ai5-"],.nx-ai5-hover');if(!b)return;
  e.preventDefault();e.stopPropagation();
  const a=b.dataset.act;
  if(a==='ai5-deep')retry('deep');else if(a==='ai5-fast')retry('fast');
  else speak(b.closest('.msg.nox'));
},true);
W.addEventListener('nox-chat-activity',e=>{busy=!!e.detail?.active;if(busy&&speaking)stopSpeak();schedule();});

/* ---------- B23: голосовой ввод ---------- */
const SR=W.SpeechRecognition||W.webkitSpeechRecognition;let rec=null,mic=null;
function micToggle(){
  if(rec){try{rec.stop();}catch{}return;}
  let base=getPrompt();if(base&&!/\s$/.test(base))base+=' ';let fin='';
  try{rec=new SR();}catch{toast('Микрофон недоступен','warn');return;}
  rec.lang='ru-RU';rec.interimResults=true;rec.continuous=true;
  rec.onresult=e=>{let interim='';for(let i=e.resultIndex;i<e.results.length;i++){const r=e.results[i];if(r.isFinal)fin+=r[0].transcript;else interim+=r[0].transcript;}setPrompt(base+fin+interim);};
  rec.onerror=e=>{if(e.error&&e.error!=='aborted'&&e.error!=='no-speech')toast('Микрофон: '+e.error,'warn');};
  rec.onend=()=>{rec=null;mic?.classList.remove('is-rec');mic?.setAttribute('aria-pressed','false');};
  try{rec.start();mic.classList.add('is-rec');mic.setAttribute('aria-pressed','true');}catch{rec=null;toast('Микрофон недоступен','warn');}
}
function ensureMic(){
  if(!SR||D.querySelector('.nx-ai5-mic'))return;
  const f=D.getElementById('chatForm');if(!f)return;
  mic=D.createElement('button');mic.type='button';mic.className='nx-ai5-mic';mic.setAttribute('aria-label','Голосовой ввод (ru-RU)');mic.title='Голосовой ввод';mic.setAttribute('aria-pressed','false');
  mic.innerHTML='<span class="nx-ai5-ring" aria-hidden="true"></span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM5 11a7 7 0 0 0 14 0M12 18v3" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>';
  mic.addEventListener('click',e=>{e.preventDefault();micToggle();});
  const bar=f.querySelector('.chat-composer-actions');if(bar)bar.prepend(mic);else f.append(mic);
}

function init(){
  ensureMic();ensureRow();
  const m=msgs();if(m)new MutationObserver(schedule).observe(m,{childList:true,subtree:true});
  if(TTS){try{speechSynthesis.addEventListener?.('voiceschanged',()=>{});}catch{}W.addEventListener('pagehide',stopSpeak);}
}
W.NoxAI5={retry,speak:m=>speak(m||lastNox()),stop:stopSpeak,plain,mic:()=>SR&&micToggle(),refresh:ensureRow,lastMode:null,
  get supported(){return{tts:TTS,stt:!!SR};}};
D.readyState==='loading'?D.addEventListener('DOMContentLoaded',init):init();
})();
