/* NOX V14 · AI6 — B25 свои шаблоны запросов · B28 реальный TTFT · B30 режим «только суть» */
(()=>{'use strict';if(window.NOX_V14_AI6)return;window.NOX_V14_AI6=1;
const D=document,TPL_KEY='nox.v14.tpl',GIST_KEY='nox.v14.gist',TPL_MAX=50;
const toast=(t,k,ms)=>{try{window.NoxToast&&window.NoxToast(t,k||'info',ms||1800)}catch{}};
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const el=(t,c,h)=>{const e=D.createElement(t);if(c)e.className=c;if(h!=null)e.innerHTML=h;return e};
const sec=ms=>(ms/1000).toFixed(1).replace('.',',')+' с';
const ls={get(k,d){try{const v=localStorage.getItem(k);return v==null?d:JSON.parse(v)}catch{return d}},set(k,v){try{localStorage.setItem(k,JSON.stringify(v));return true}catch{return false}}};

/* ---------- поле ввода (обычный textarea или Loquix в shadow DOM) ---------- */
function loq(){const c=D.querySelector('loquix-chat-composer');return c&&c.shadowRoot&&c.shadowRoot.querySelector('loquix-prompt-input')}
function getPrompt(){const l=loq();if(l)return String(l.value||'');const p=D.getElementById('prompt');return p?p.value:''}
function setPrompt(v){const l=loq();
 if(l){l.value=v;l.dispatchEvent(new CustomEvent('loquix-change',{bubbles:true,composed:true,detail:{value:v}}));const a=l.shadowRoot&&l.shadowRoot.querySelector('textarea');try{(a||l).focus()}catch{}return true}
 const p=D.getElementById('prompt');if(!p)return false;p.value=v;p.dispatchEvent(new Event('input',{bubbles:true}));try{p.focus();p.setSelectionRange(v.length,v.length)}catch{}return true}

/* ================= B25 · шаблоны ================= */
const tpl={
 list(){const a=ls.get(TPL_KEY,[]);return Array.isArray(a)?a.filter(x=>x&&typeof x.text==='string'&&x.text.trim()):[]},
 add(text){text=String(text||'').trim();if(!text){toast('Поле ввода пустое — нечего сохранять','warn');return null}
  const a=tpl.list();const dup=a.find(x=>x.text===text);if(dup){toast('Такой шаблон уже есть','info');return dup}
  if(a.length>=TPL_MAX){toast('Лимит '+TPL_MAX+' шаблонов — удалите лишние','warn',2600);return null}
  const it={id:Date.now().toString(36)+Math.random().toString(36).slice(2,6),text,t:Date.now()};a.unshift(it);
  if(!ls.set(TPL_KEY,a)){toast('Не удалось сохранить (хранилище недоступно)','warn');return null}
  toast('Шаблон сохранён · '+a.length+'/'+TPL_MAX,'ok');drawTpl();return it},
 remove(id){const a=tpl.list().filter(x=>x.id!==id);ls.set(TPL_KEY,a);drawTpl();return a.length},
 insert(id){const it=tpl.list().find(x=>x.id===id);if(!it)return false;const ok=setPrompt(it.text);if(ok)toast('Шаблон подставлен','info',1200);hidePanel();return ok}
};
let bar,panel,gistBtn;
function title(t){const s=t.replace(/\s+/g,' ').trim();return s.length>70?s.slice(0,70)+'…':s}
function drawTpl(){if(!panel)return;const a=tpl.list();const box=panel.querySelector('.nx6-list');
 panel.querySelector('.nx6-count').textContent=a.length+'/'+TPL_MAX;
 if(!a.length){box.innerHTML='<p class="nx6-empty">Шаблонов пока нет. Напишите запрос и нажмите «＋ Шаблон».</p>';return}
 box.innerHTML='';a.forEach(it=>{const row=el('div','nx6-row');
  const b=el('button','nx6-ins',`<span>${esc(title(it.text))}</span>`);b.type='button';b.title='Подставить в поле ввода';b.onclick=()=>tpl.insert(it.id);
  const x=el('button','nx6-del','×');x.type='button';x.title='Удалить шаблон';x.setAttribute('aria-label','Удалить шаблон «'+title(it.text)+'»');x.onclick=()=>{tpl.remove(it.id);toast('Шаблон удалён','info',1200)};
  row.append(b,x);box.append(row)})}
function hidePanel(){if(panel){panel.hidden=true;bar&&bar.querySelector('.nx6-open')?.setAttribute('aria-expanded','false')}}
function togglePanel(){if(!panel)return;panel.hidden=!panel.hidden;bar.querySelector('.nx6-open').setAttribute('aria-expanded',String(!panel.hidden));if(!panel.hidden)drawTpl()}

/* ================= B30 · только суть ================= */
const gist={get(){return ls.get(GIST_KEY,false)===true},
 set(v){ls.set(GIST_KEY,!!v);syncGistBtn();applyGist();toast(v?'Режим «только суть» включён':'Режим «только суть» выключен','info',1400);return !!v},
 toggle(){return gist.set(!gist.get())}};
function syncGistBtn(){if(gistBtn){const on=gist.get();gistBtn.setAttribute('aria-pressed',String(on));gistBtn.classList.toggle('on',on)}}
function isLong(t){return t.length>900||t.split('\n').length>12}
function bodyOf(m){return [...m.children].find(c=>c.tagName==='DIV'&&!c.classList.contains('nx6-ttft'))}
function unclip(m){m.classList.remove('nx6-clip','nx6-open');m.querySelector(':scope>.nx6-more')?.remove()}
function applyGist(){const box=D.getElementById('messages');if(!box)return;const on=gist.get();const all=[...box.querySelectorAll('.msg.nox')];
 const streamingEl=run&&!run.done?run.el:null;
 all.forEach(m=>{const b=bodyOf(m);
  if(!on||!b||m===streamingEl||(run&&!run.done&&m===all[all.length-1])){unclip(m);return}
  if(!isLong(b.textContent||'')){unclip(m);return}
  if(m.querySelector(':scope>.nx6-more'))return;
  m.classList.add('nx6-clip');const btn=el('button','nx6-more','<span>развернуть</span>');btn.type='button';btn.setAttribute('aria-expanded','false');
  btn.onclick=()=>{const o=m.classList.toggle('nx6-open');btn.setAttribute('aria-expanded',String(o));btn.firstChild.textContent=o?'свернуть':'развернуть'};
  b.after(btn)})}

/* ================= B28 · TTFT ================= */
let run=null;const history=[];
window.NOX_TTFT=null;
function publish(r){const o={ok:r.ttft!=null,ttft_ms:r.ttft!=null?Math.round(r.ttft):null,total_ms:r.total!=null?Math.round(r.total):null,status:r.status,at:new Date(r.wall).toISOString()};window.NOX_TTFT=o;
 try{window.dispatchEvent(new CustomEvent('nox-ttft',{detail:o}))}catch{}}
function badgeText(r){if(r.status==='wait')return '⚡ первый токен · ожидание…';
 const a='⚡ первый токен '+(r.ttft!=null?sec(r.ttft):'Н/Д');
 if(r.status==='stream')return a+' · поток…';
 return a+' · всего '+(r.total!=null&&r.status==='done'?sec(r.total):'Н/Д')}
function putBadge(m,r){let b=m.querySelector(':scope>.nx6-ttft');if(!b){b=el('div','nx6-ttft');b.setAttribute('aria-label','Время ответа NOX');m.append(b)}
 b.classList.toggle('na',r.ttft==null&&r.status!=='wait'&&r.status!=='stream');b.classList.toggle('live',r.status==='wait'||r.status==='stream');
 const t=badgeText(r);if(b.textContent!==t)b.textContent=t;
 b.title=r.ttft!=null?'Измерено в браузере: от отправки POST /api/chat до первого непустого message.content':'Время первого токена измерить не удалось'}
function paintBadges(){const box=D.getElementById('messages');if(!box)return;const all=[...box.querySelectorAll('.msg.nox')];const keep=new Set();const putBadge0=putBadge;const putBadge=(m,r)=>{keep.add(m);putBadge0(m,r)};
 if(run&&!run.done){const m=run.el&&run.el.isConnected?run.el:all[all.length-1];if(m)putBadge(m,run)}
 const last=[...all].reverse().find(m=>{const t=(bodyOf(m)?.textContent||'').trim();return t&&history.some(h=>h.text&&h.text.trim()===t)});
 if(last&&!(run&&!run.done&&last===run.el)){const t=bodyOf(last).textContent.trim();const h=history.find(h=>h.text.trim()===t);if(h)putBadge(last,h)}
 else if(run&&run.done&&!run.text&&all.length){/* ошибка без текста — бейдж Н/Д у последнего ответа */const m=run.el&&run.el.isConnected?run.el:null;if(m)putBadge(m,run)}
 all.forEach(m=>{if(!keep.has(m)){const b=m.querySelector(':scope>.nx6-ttft');if(b)b.remove()}})}
function finish(r,status){if(r.done)return;r.done=true;r.status=status;if(status==='done')r.total=performance.now()-r.t0;
 if(r.text){history.unshift(r);history.length=Math.min(history.length,20)}publish(r);schedule()}
async function readCopy(r,resp){const reader=resp.body.getReader();const dec=new TextDecoder();let buf='';
 try{for(;;){const c=await reader.read();if(c.done)break;buf+=dec.decode(c.value,{stream:true});let p;
  while((p=buf.indexOf('\n'))!==-1){const raw=buf.slice(0,p).trim();buf=buf.slice(p+1);if(!raw)continue;let f;try{f=JSON.parse(raw)}catch{continue}
   if(f.error){finish(r,'error');return}
   const c2=f.message&&f.message.content;if(c2){if(r.ttft==null){r.ttft=performance.now()-r.t0;r.status='stream';publish(r)}r.text+=c2}
   if(f.done===true){finish(r,'done');return}}}
  const tail=buf.trim();if(tail){try{const f=JSON.parse(tail);const c2=f.message&&f.message.content;if(c2){if(r.ttft==null)r.ttft=performance.now()-r.t0;r.text+=c2}if(f.done===true){finish(r,'done');return}}catch{}}
  finish(r,'cut')}catch{finish(r,'abort')}}
const prevFetch=window.fetch;
window.fetch=function(input,init){
 let path='',method='GET',mini=false;
 try{path=new URL(typeof input==='string'?input:(input&&input.url)||String(input),location.href).pathname;method=String((init&&init.method)||(input&&input.method)||'GET').toUpperCase();
  const body=init&&init.body;if(typeof body==='string'&&/"mini"\s*:\s*true/.test(body))mini=true}catch{}
 const p=prevFetch.apply(this,arguments);
 if(path!=='/api/chat'||method!=='POST'||mini)return p;
 let r;try{const box=D.getElementById('messages');const all=box?box.querySelectorAll('.msg.nox'):[];
  r={t0:performance.now(),wall:Date.now(),ttft:null,total:null,status:'wait',text:'',done:false,el:all.length?all[all.length-1]:null};
  if(run&&!run.done)finish(run,'abort');run=r;publish(r);schedule()}catch{return p}
 return p.then(resp=>{try{if(!resp||!resp.ok||!resp.body||typeof resp.clone!=='function'){finish(r,'error');return resp}
   const copy=resp.clone();readCopy(r,copy)}catch{finish(r,'error')}return resp},
  err=>{finish(r,'error');throw err})};

/* ---------- наблюдатель за #messages ---------- */
let raf=0,mo=null;
function schedule(){if(raf)return;raf=requestAnimationFrame(()=>{raf=0;if(mo)mo.disconnect();try{paintBadges();applyGist()}finally{observe()}})}
function observe(){const box=D.getElementById('messages');if(!box)return;if(!mo)mo=new MutationObserver(schedule);mo.observe(box,{childList:true,subtree:true,characterData:true})}
window.addEventListener('nox-chat-activity',schedule);
let tick=0;setInterval(()=>{if(run&&!run.done&&run.status==='wait'){if(++tick%2===0)schedule()}},500);

/* ---------- UI: полоса у поля ввода ---------- */
function mount(){const form=D.getElementById('chatForm');if(!form||D.querySelector('.nx6-bar'))return;
 bar=el('div','nx6-bar');bar.setAttribute('role','toolbar');bar.setAttribute('aria-label','Шаблоны и режим ответа');
 bar.innerHTML='<button type="button" class="nx6-b nx6-save" title="Сохранить текст поля ввода как шаблон"><i>＋</i><span>Шаблон</span></button>'+
  '<button type="button" class="nx6-b nx6-open" aria-expanded="false" aria-haspopup="true" title="Мои шаблоны"><i>☰</i><span>Мои шаблоны</span></button>'+
  '<button type="button" class="nx6-b nx6-gist" aria-pressed="false" title="Сворачивать длинные ответы NOX до сути"><i>◆</i><span>Только суть</span></button>';
 panel=el('div','nx6-panel');panel.hidden=true;panel.setAttribute('role','dialog');panel.setAttribute('aria-label','Мои шаблоны');
 panel.innerHTML='<div class="nx6-ph"><b>МОИ ШАБЛОНЫ</b><span class="nx6-count"></span><button type="button" class="nx6-x" aria-label="Закрыть">×</button></div><div class="nx6-list"></div>';
 form.before(bar);bar.append(panel);
 bar.querySelector('.nx6-save').onclick=()=>tpl.add(getPrompt());
 bar.querySelector('.nx6-open').onclick=togglePanel;panel.querySelector('.nx6-x').onclick=hidePanel;
 gistBtn=bar.querySelector('.nx6-gist');gistBtn.onclick=()=>gist.toggle();syncGistBtn();
 D.addEventListener('keydown',e=>{if(e.key==='Escape'&&panel&&!panel.hidden)hidePanel()});
 D.addEventListener('pointerdown',e=>{if(panel&&!panel.hidden&&!bar.contains(e.target))hidePanel()},true);
 drawTpl()}

/* ---------- палитра Ctrl+K ---------- */
function hookPalette(){const p=D.querySelector('.nv-pal');if(!p||p.dataset.nx6)return!!p;p.dataset.nx6='1';
 new MutationObserver(()=>{if(p.hidden)return;const list=p.querySelector('#nvList');if(!list||list.querySelector('.nx6-grp'))return;
  const q=(p.querySelector('#nvQ')?.value||'').trim().toLowerCase();
  const rows=[];const gl='только суть свернуть длинные ответы gist';
  if(!q||gl.includes(q))rows.push(['Режим «только суть»: '+(gist.get()?'выключить':'включить'),'Сворачивать длинные ответы NOX',()=>gist.toggle()]);
  if(!q)rows.push(['Сохранить поле ввода как шаблон','Шаблоны · '+tpl.list().length+'/'+TPL_MAX,()=>tpl.add(getPrompt())]);
  tpl.list().filter(t=>!q||t.text.toLowerCase().includes(q)||'шаблон'.includes(q)).slice(0,q?8:12).forEach(t=>rows.push([title(t.text),'Мой шаблон · подставить',()=>tpl.insert(t.id)]));
  if(!rows.length)return;
  list.append(el('div','nv-grp nx6-grp','Мои шаблоны'));
  rows.forEach(([t,d,f])=>{const b=el('button','nv-row nx6-prow',`<span>${esc(t)}</span><small>${esc(d)}</small>`);b.type='button';b.onclick=()=>{p.hidden=true;f()};list.append(b)})})
 .observe(p,{attributes:true,childList:true,subtree:true});return true}

function start(){mount();observe();schedule();hookPalette()}
if(D.readyState!=='loading')start();else D.addEventListener('DOMContentLoaded',start);
setTimeout(start,1500);setTimeout(hookPalette,3000);
window.addEventListener('storage',e=>{if(e.key===TPL_KEY)drawTpl();if(e.key===GIST_KEY){syncGistBtn();applyGist()}});

window.NoxAI6={version:'v14-ai6',templates:tpl,gist,ttft:()=>window.NOX_TTFT,getPrompt,setPrompt,refresh:schedule};
})();
