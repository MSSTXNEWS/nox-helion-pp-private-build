/* V14 AI2 — B10 журнал решений, B12 напоминания (+бейдж просроченных), B13 заметка → напоминание, B19 починка «Ветки». Без <select>; нет сервера → «Н/Д · HOLD». */
(()=>{'use strict';if(window.NOX_V14_AI2)return;window.NOX_V14_AI2=1;
const D=document;
const el=(t,c,h)=>{const e=D.createElement(t);if(c)e.className=c;if(h!=null)e.innerHTML=h;return e};
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const toast=(t,k,ms)=>{try{window.NoxToast&&window.NoxToast(t,k,ms)}catch{}};
const HOLD='Н/Д · HOLD';
async function api(path,body){const o=body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{};
 const r=await fetch(path,{credentials:'same-origin',...o});if(!r.ok)throw Error('HTTP '+r.status);const d=await r.json();if(!d||typeof d!=='object')throw Error('bad json');return d}
/* время: ISO / секунды / мс → МСК */
function toMs(v){if(v==null||v==='')return NaN;if(typeof v==='number')return v<1e12?v*1000:v;const n=Number(v);if(/^\d+(\.\d+)?$/.test(String(v)))return n<1e12?n*1000:n;return Date.parse(v)}
const MSK=new Intl.DateTimeFormat('ru-RU',{timeZone:'Europe/Moscow',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
const msk=v=>{const t=toMs(v);return isFinite(t)?MSK.format(t)+' МСК':'Н/Д'};
/* модалка */
function modal(cls,title,body){D.querySelector('.'+cls)?.remove();const m=el('div','nw-modal nx2-modal '+cls,`<div class="nw-modal-box" role="dialog" aria-modal="true" aria-label="${esc(title)}"><h3>${esc(title)}</h3><div class="nx2-body">${body}</div><div class="nx2-foot"><button type="button" class="ok" data-x2="close">Закрыть</button></div></div>`);
 m.addEventListener('click',e=>{if(e.target===m||e.target.closest('[data-x2=close]'))m.remove()});m.addEventListener('keydown',e=>{if(e.key==='Escape'){e.stopPropagation();m.remove()}});D.body.append(m);m.querySelector('[data-x2=close]').focus();return m}
const holdHtml=why=>`<p class="nx2-hold"><b>${HOLD}</b><span>${esc(why)}</span></p>`;

/* ---------- B10 журнал решений ---------- */
async function decisions(){if(typeof window.NoxAI?.decisions==='function')return window.NoxAI.decisions();
 const m=modal('nx2-dec','Журнал решений','<p class="nx2-load">Загрузка…</p>');const b=m.querySelector('.nx2-body');
 try{const d=await api('/api/nox/decisions');const L=Array.isArray(d.decisions)?d.decisions:[];
  const lv=d.levels&&typeof d.levels==='object'?Object.entries(Array.isArray(d.levels)?Object.fromEntries(d.levels.map((x,i)=>[i,x])):d.levels):[];
  b.innerHTML=`<p class="nx2-st">Статус сервера: <b>${esc(d.status||'Н/Д')}</b> · записей: ${L.length}</p>`+
   (lv.length?`<div class="nx2-lv">${lv.map(([k,v])=>`<span><b>${esc(k)}</b> ${esc(typeof v==='object'?JSON.stringify(v):v)}</span>`).join('')}</div>`:'')+
   (L.length?`<ol class="nx2-list">${L.slice(0,200).map(x=>`<li><div class="nx2-row"><b>${esc(x.decision||'Н/Д')}</b>${x.level!=null?`<em class="nx2-tag">${esc(x.level)}</em>`:''}${x.status?`<em class="nx2-tag">${esc(x.status)}</em>`:''}</div><small>${esc(msk(x.t))}</small>${x.reason?`<p>${esc(x.reason)}</p>`:''}${x.basis?`<p class="nx2-basis">Основание: ${esc(typeof x.basis==='object'?JSON.stringify(x.basis):x.basis)}</p>`:''}</li>`).join('')}</ol>`:'<p>Решений пока нет.</p>')}
 catch(e){b.innerHTML=holdHtml('Мост NOX не ответил на /api/nox/decisions ('+(e.message||e)+'). Данные не показаны.')}}

/* ---------- B12 напоминания ---------- */
let remCache=null;
const overdue=(list,now)=>list.filter(r=>!r.done&&isFinite(toMs(r.due))&&toMs(r.due)<=now).length;
async function loadRem(){const d=await api('/api/nox/reminders');const list=Array.isArray(d.reminders)?d.reminders:[];const now=isFinite(toMs(d.now))?toMs(d.now):Date.now();remCache={d,list,now};return remCache}
function drawRem(b,{d,list,now}){const sorted=list.slice().sort((a,c)=>(toMs(a.due)||9e15)-(toMs(c.due)||9e15));
 b.innerHTML=`<p class="nx2-st">Статус: <b>${esc(d.status||'Н/Д')}</b> · всего ${list.length} · просрочено ${overdue(list,now)} · сервер: ${esc(msk(now))}</p>`+
 (sorted.length?`<ul class="nx2-list nx2-rem">${sorted.map(r=>{const late=isFinite(toMs(r.due))&&toMs(r.due)<=now;return `<li class="${late?'late':''}" data-id="${esc(r.id)}"><div class="nx2-row"><span class="nx2-txt">${esc(r.text||'(без текста)')}</span><button type="button" class="nx2-done" data-x2="done" data-id="${esc(r.id)}">Выполнено</button></div><small>${late?'Просрочено · ':''}${esc(msk(r.due))}</small></li>`}).join('')}</ul>`:'<p>Активных напоминаний нет.</p>')}
async function reminders(){const m=modal('nx2-remm','Напоминания','<p class="nx2-load">Загрузка…</p>');const b=m.querySelector('.nx2-body');
 const reload=async()=>{try{drawRem(b,await loadRem());badge()}catch(e){b.innerHTML=holdHtml('Мост NOX не ответил на /api/nox/reminders ('+(e.message||e)+').');setBadge(null)}};
 b.addEventListener('click',async e=>{const x=e.target.closest('[data-x2=done]');if(!x)return;x.disabled=true;x.textContent='…';
  try{const r=await api('/api/nox/reminders/done',{id:x.dataset.id});if(r.status&&!/^(ok|done|ready|success)$/i.test(String(r.status)))throw Error(r.status);toast('Напоминание выполнено','ok',1600);await reload()}
  catch(err){x.disabled=false;x.textContent='Выполнено';toast('HOLD · сервер не подтвердил выполнение','error',2600)}});
 await reload()}
/* бейдж просроченных */
let badgeEl=null;
function setBadge(n){if(!badgeEl){badgeEl=el('button','nx2-badge');badgeEl.type='button';badgeEl.hidden=true;badgeEl.onclick=reminders;
  (D.querySelector('.nox-v14-bar')||D.body).append(badgeEl);if(!badgeEl.parentElement.classList.contains('nox-v14-bar'))badgeEl.classList.add('nx2-float')}
 if(!n){badgeEl.hidden=true;return}badgeEl.hidden=false;badgeEl.innerHTML=`<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 2a4 4 0 0 0-4 4v3l-1.5 2h11L12 9V6a4 4 0 0 0-4-4zM6.5 13a1.5 1.5 0 0 0 3 0" fill="none" stroke="currentColor" stroke-width="1.4"/></svg><b>${n>99?'99+':n}</b>`;
 badgeEl.title=badgeEl.ariaLabel='Просроченные напоминания: '+n}
async function badge(){if(D.hidden)return;try{const c=remCache&&Date.now()-(remCache.at||0)<2000?remCache:await loadRem();c.at=c.at||Date.now();setBadge(overdue(c.list,c.now))}catch{setBadge(null)}}
let pollT=null;function poll(){clearInterval(pollT);pollT=setInterval(()=>{if(!D.hidden)badge()},60000)}
D.addEventListener('visibilitychange',()=>{if(!D.hidden)badge()});

/* ---------- B13 заметка → напоминание ---------- */
function noteDialog(){const m=modal('nx2-note','Заметка / напоминание',`<label class="nx2-lbl" for="nx2NoteIn">Текст. Например: «напомни через 10 мин проверить сервер»</label><textarea id="nx2NoteIn" rows="3" maxlength="4000"></textarea><div class="nx2-actions"><button type="button" class="ok" data-x2="save">Сохранить</button></div><p class="nx2-res" aria-live="polite"></p>`);
 const ta=m.querySelector('#nx2NoteIn'),res=m.querySelector('.nx2-res'),sv=m.querySelector('[data-x2=save]');ta.focus();
 const go=async()=>{const text=ta.value.trim();if(!text){ta.focus();return}sv.disabled=true;res.textContent='Отправка…';
  try{const page=(location.pathname.split('/').pop()||'index.html');const d=await api('/api/nox/notes',{text,page,remind:true});
   if(d.status&&/hold|error|fail/i.test(String(d.status)))throw Error(d.status);const n=d.note||{};
   const due=n.reminder?.due??n.remind_at??n.due??n.reminder_due??d.reminder?.due??null;const made=n.reminder?!!n.reminder:(due!=null||n.remind===true&&due!=null);
   res.innerHTML=`<b>Заметка сохранена.</b> `+(made&&due!=null?`Напоминание создано на <b>${esc(msk(due))}</b>.`:'Напоминание не создано: сервер не нашёл время в тексте.');
   ta.value='';remCache=null;badge()}
  catch(e){res.innerHTML=holdHtml('Мост NOX не принял заметку ('+(e.message||e)+'). Ничего не сохранено.')}finally{sv.disabled=false}};
 sv.onclick=go;ta.addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();go()}})}

/* ---------- палитра Ctrl+K ---------- */
const ITEMS=()=>[...(typeof window.NoxAI?.decisions==='function'?[]:[['Журнал решений','B10',decisions]]),['Напоминания','B12',reminders],['Заметка / напоминание…','B13',noteDialog]];
function hookPalette(){const p=D.querySelector('.nv-pal');if(!p||p.dataset.nx2)return;p.dataset.nx2='1';
 new MutationObserver(()=>{if(p.hidden)return;const list=p.querySelector('#nvList');if(!list||list.querySelector('.nx2-grp'))return;const q=(p.querySelector('#nvQ')?.value||'').trim().toLowerCase();
  const it=ITEMS().filter(([t])=>!q||t.toLowerCase().includes(q)||'напоминание заметка решения журнал'.includes(q));
  const have=new Set([...list.querySelectorAll('.nv-row span')].map(s=>s.textContent.trim()));const add=it.filter(([t])=>!have.has(t));if(!add.length)return;
  list.append(el('div','nv-grp nx2-grp','NOX · память и решения'));add.forEach(([t,d,f])=>{const b=el('button','nv-row nx2-pr',`<span>${esc(t)}</span><small>${esc(d)}</small>`);b.type='button';b.onclick=()=>{p.hidden=true;f()};list.append(b)})}).observe(p,{attributes:true,childList:true,subtree:true})}

/* ---------- B19 «Ветка» ----------
 Причина: nox-v14-live.js на каждую мутацию #messages вызывает lucide.createIcons(), а lucide заменяет ВСЕ [data-lucide], включая уже готовые <svg data-lucide>
 (иконка кнопки «Редактировать» внутри #messages) → новая мутация → бесконечный цикл (~10 раз/с). Из-за него debounce-сканеры nox-v14-wow.js/more.js
 никогда не срабатывают: ряд .nw-acts (и кнопка «Ветка» в нём) не появляется. Кроме того, поле ввода — textarea#prompt внутри shadow DOM loquix,
 поэтому document.getElementById('prompt') там = null. Исправление: обёртка createIcons не трогает уже отрисованные svg; запасной делегированный обработчик
 заполняет поле, если штатный путь (кнопка edit-message) не сработал. */
function fixIcons(){const L=window.lucide;if(!L||typeof L.createIcons!=='function'||L.createIcons.nx2)return;const orig=L.createIcons;
 const w=function(...a){const svgs=[...D.querySelectorAll('svg[data-lucide]')];const names=svgs.map(s=>s.getAttribute('data-lucide'));svgs.forEach(s=>s.removeAttribute('data-lucide'));
  try{return orig.apply(this,a)}finally{svgs.forEach((s,i)=>s.setAttribute('data-lucide',names[i]))}};w.nx2=1;try{L.createIcons=w}catch{}}
function promptInput(){const c=D.querySelector('loquix-chat-composer');const pi=c?.shadowRoot?.querySelector('loquix-prompt-input');const ta=pi?.shadowRoot?.querySelector('textarea')||D.getElementById('prompt');return{c,pi,ta}}
function promptValue(){const{pi,ta}=promptInput();return String(pi?.value??ta?.value??'')}
function setPrompt(v){const{pi,ta}=promptInput();if(pi){pi.value=v;pi.dispatchEvent(new CustomEvent('loquix-change',{bubbles:true,composed:true,detail:{value:v}}))}
 if(ta){ta.value=v;ta.dispatchEvent(new Event('input',{bubbles:true,composed:true}));try{ta.focus()}catch{}}return!!(pi||ta)}
D.addEventListener('click',e=>{const b=e.target.closest?.('[data-nl-a=branch]');if(!b)return;const m=b.closest('.msg');let n=m?.previousElementSibling;while(n&&!n.classList.contains('me'))n=n.previousElementSibling;
 const q=(n?.querySelector(':scope>div')?.innerText||'').trim();if(!q)return;const eb=n.querySelector('[data-action=edit-message]');if(eb?.disabled)return;
 setTimeout(()=>{if(!promptValue().trim()){setPrompt(q);toast('Запрос перенесён в поле ввода','info',2000)}},80)});
function api2(){return{decisions,reminders,note:noteDialog,refreshBadge:badge,setPrompt,promptValue,version:'ai2-1'}}
window.NoxAI2=api2();
function start(){fixIcons();hookPalette()}
if(D.readyState!=='loading')start();else D.addEventListener('DOMContentLoaded',start);
setTimeout(()=>{start();badge();poll()},1200);setTimeout(start,3000);
})();
