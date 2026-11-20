/* NOX V14 · AI3 — цитата (B22), история запросов (B26), счётчик слов (B27), эмоция ядра (B29) */
(()=>{'use strict';if(window.NOX_V14_AI3)return;window.NOX_V14_AI3=1;
const D=document,LS=window.localStorage,W=window;
const K_HIST='nox.v14.hist';
const toast=(t,k='info',ms=2200)=>{try{W.NoxToast?W.NoxToast(t,k,ms):0}catch{}};
const el=(t,c,h)=>{const e=D.createElement(t);if(c)e.className=c;if(h!=null)e.innerHTML=h;return e};
const rd=(k,d)=>{try{const v=JSON.parse(LS.getItem(k));return v??d}catch{return d}};
const wr=(k,v)=>{try{LS.setItem(k,JSON.stringify(v))}catch{}};
const words=s=>{s=String(s||'').trim();return s?s.split(/\s+/).length:0};

/* ---------- поле ввода (light DOM textarea или Loquix в shadow DOM) ---------- */
function prompt(){const l=D.getElementById('prompt');if(l)return{ta:l,pi:null};
 const c=D.querySelector('loquix-chat-composer'),pi=c?.shadowRoot?.querySelector('loquix-prompt-input'),ta=pi?.shadowRoot?.querySelector('textarea');return{ta:ta||null,pi:pi||null}}
const isPrompt=e=>{const t=e.composedPath?e.composedPath()[0]:e.target;return !!(t&&t.id==='prompt'&&t.tagName==='TEXTAREA')};
function getPrompt(){const{ta,pi}=prompt();return String(ta?.value??pi?.value??'')}
function setPrompt(v,focus=true){const{ta,pi}=prompt();if(!ta)return false;
 if(pi)pi.value=v;ta.value=v;ta.dispatchEvent(new Event('input',{bubbles:true,composed:true}));
 const fin=()=>{try{ta.value!==v&&(ta.value=v);if(focus)ta.focus();ta.setSelectionRange(v.length,v.length);ta.scrollTop=ta.scrollHeight}catch{}counter()};
 fin();if(pi&&pi.updateComplete)pi.updateComplete.then(fin).catch(()=>{});return true}

/* ---------- панель у поля ввода ---------- */
let bar,cnt,soulChip;
function buildBar(){const form=D.getElementById('chatForm');if(!form||form.querySelector('.nx3-bar'))return;
 bar=el('div','nx3-bar');bar.setAttribute('aria-label','Состояние запроса');
 soulChip=el('span','nx3-chip nx3-soul na','эмоция: Н/Д');soulChip.title='Эмоция ядра (/api/nox/soul)';
 cnt=el('span','nx3-cnt','0 сл. · 0 симв.');
 bar.append(soulChip,cnt);const actions=form.querySelector('.chat-composer-actions');actions?form.insertBefore(bar,actions):form.append(bar);
 if(W.NOX_SOUL!==undefined)setSoul(soulEm(W.NOX_SOUL),W.NOX_SOUL);counter()}
function counter(){if(!cnt)return;const v=getPrompt();cnt.textContent=words(v)+' сл. · '+v.length+' симв.';cnt.title='Слов: '+words(v)+', символов: '+v.length}

/* ---------- B26 история ---------- */
const hist=()=>{const a=rd(K_HIST,[]);return Array.isArray(a)?a.filter(x=>typeof x==='string'):[]};
let lastPush={t:'',at:0};
function pushHist(t){t=String(t||'').trim();if(!t)return;const now=Date.now();if(t===lastPush.t&&now-lastPush.at<2000)return;lastPush={t,at:now};
 let a=hist();if(a[a.length-1]===t)a.pop();a.push(t);if(a.length>100)a=a.slice(-100);wr(K_HIST,a);hIdx=-1;hVal=null}
let hIdx=-1,hVal=null;
function onKey(e){if(!isPrompt(e)||e.isComposing)return;const ta=e.composedPath()[0];
 if(e.key==='Enter'&&!e.shiftKey&&!e.ctrlKey&&!e.altKey&&!e.metaKey){pushHist(ta.value);return}
 if((e.key!=='ArrowUp'&&e.key!=='ArrowDown')||e.shiftKey||e.altKey||e.ctrlKey||e.metaKey)return;
 const v=ta.value,fromHist=hVal!==null&&v===hVal,atStart=ta.selectionStart===0&&ta.selectionEnd===0;
 if(!(v===''||(fromHist&&atStart)||(fromHist&&e.key==='ArrowDown'&&ta.selectionStart===v.length)))return;
 const a=hist();if(!a.length)return;
 if(!fromHist)hIdx=-1;
 if(e.key==='ArrowUp'){const n=hIdx===-1?a.length-1:Math.max(0,hIdx-1);e.preventDefault();hIdx=n;hVal=a[n];setPrompt(a[n]);try{ta.setSelectionRange(0,0)}catch{};queueMicrotask(()=>{try{ta.setSelectionRange(0,0)}catch{}})}
 else{if(hIdx===-1||!fromHist)return;e.preventDefault();if(hIdx>=a.length-1){hIdx=-1;hVal=null;setPrompt('')}else{hIdx++;hVal=a[hIdx];setPrompt(a[hIdx])}}}
D.addEventListener('keydown',onKey,true);
D.addEventListener('submit',e=>{if(e.target&&e.target.id==='chatForm')pushHist(getPrompt())},true);
D.addEventListener('loquix-submit',e=>pushHist(e.detail?.content),true);
D.addEventListener('click',e=>{const b=e.target.closest?.('#chatForm button[type=submit],#chatForm [data-action=send]');if(b&&!b.disabled)pushHist(getPrompt())},true);
D.addEventListener('input',e=>{if(isPrompt(e)){counter();const v=e.composedPath()[0].value;if(hVal!==null&&v!==hVal){hIdx=-1;hVal=null}}},true);

/* ---------- B22 цитата ---------- */
let qBtn;
function selInNox(){const s=getSelection();if(!s||s.isCollapsed||!s.rangeCount)return null;const t=s.toString().trim();if(!t)return null;
 const r=s.getRangeAt(0);const n=r.commonAncestorContainer;const host=(n.nodeType===1?n:n.parentElement)?.closest('#messages .msg.nox');
 if(!host||host.querySelector('footer.nx3-meta')?.contains(n))return null;return{t,r}}
function showQuote(){const x=selInNox();if(!x){hideQuote();return}
 if(!qBtn){qBtn=el('button','nx3-quote','❝ Цитировать');qBtn.type='button';qBtn.hidden=true;D.body.append(qBtn);
  qBtn.addEventListener('pointerdown',e=>e.preventDefault());qBtn.addEventListener('mousedown',e=>e.preventDefault());
  qBtn.onclick=()=>{const y=selInNox();if(y)quote(y.t);hideQuote();try{getSelection().removeAllRanges()}catch{}}}
 const rect=x.r.getBoundingClientRect(),vw=D.documentElement.clientWidth;qBtn.hidden=false;const w=qBtn.offsetWidth||110,h=qBtn.offsetHeight||30;
 let top=rect.top-h-8;if(top<6)top=rect.bottom+8;qBtn.style.top=Math.min(top,innerHeight-h-6)+'px';qBtn.style.left=Math.max(6,Math.min(rect.left+rect.width/2-w/2,vw-w-6))+'px'}
function hideQuote(){if(qBtn)qBtn.hidden=true}
function quote(t){t=String(t||'').trim();if(!t)return false;const q=t.split(/\r?\n/).map(l=>'> '+l).join('\n')+'\n\n';const cur=getPrompt();
 return setPrompt(cur&&!/\n\n$/.test(cur)?cur.replace(/\s*$/,'')+'\n\n'+q:cur+q)}
let qT=0;D.addEventListener('selectionchange',()=>{if(qT)return;qT=setTimeout(()=>{qT=0;showQuote()},120)});
D.addEventListener('mouseup',()=>setTimeout(showQuote,30));D.addEventListener('keyup',e=>{if(e.shiftKey)setTimeout(showQuote,30)});
let qR=0;addEventListener('scroll',()=>{if(!qBtn||qBtn.hidden||qR)return;qR=requestAnimationFrame(()=>{qR=0;showQuote()})},{passive:true,capture:true});

/* ---------- B29 эмоция ---------- */
let soulT=0,soulBusy=false;
const soulEm=d=>d&&typeof d.emotion==='string'?d.emotion.trim():(d&&d.emotion&&typeof d.emotion==='object'&&typeof d.emotion.label==='string'?d.emotion.label.trim():'');
async function refreshSoul(){if(soulBusy)return;soulBusy=true;try{const r=await fetch('/api/nox/soul',{cache:'no-store'});let d=null;
  if(r.ok&&(r.headers.get('content-type')||'').includes('json'))d=await r.json();
  setSoul(soulEm(d),d)}catch{setSoul('',null)}finally{soulBusy=false;soulT=Date.now()}}
function setSoul(em,d){W.NOX_SOUL=d||null;if(!soulChip)return;soulChip.textContent='эмоция: '+(em||'Н/Д');soulChip.classList.toggle('na',!em);
 const aw=d&&(typeof d.awareness==='number'||typeof d.awareness==='string')?' · осознанность: '+d.awareness:'';soulChip.title=em?('Эмоция ядра: '+em+aw):'Эмоция ядра: Н/Д (нет данных /api/nox/soul)'}
setInterval(()=>{if(D.visibilityState==='visible'&&Date.now()-soulT>=59000)refreshSoul()},5000);
D.addEventListener('visibilitychange',()=>{if(D.visibilityState==='visible'&&Date.now()-soulT>=60000)refreshSoul()});

/* ---------- B27 счётчик у ответов ---------- */
const textNode=m=>m.querySelector(':scope>div:not(.nx3-meta)');
const textOf=m=>(textNode(m)?.textContent||'').trim();
let active=false;
function decorate(){const box=D.getElementById('messages');if(!box)return;
 box.querySelectorAll('.msg.nox').forEach(m=>{const txt=textOf(m);let f=m.querySelector(':scope>footer.nx3-meta');
  if(!txt){f?.remove();return}
  if(!f){f=el('footer','nx3-meta');f.innerHTML='<span class="nx3-wc"></span>';m.append(f)}
  const n=f.querySelector('.nx3-wc'),v=words(txt)+' сл. · '+txt.length+' симв.';if(n.textContent!==v)n.textContent=v})}
let decT=0;function schedule(){if(decT)return;decT=setTimeout(()=>{decT=0;decorate()},180)}
W.addEventListener('nox-chat-activity',e=>{const was=active;active=!!e.detail?.active;if(was&&!active){schedule();setTimeout(decorate,900);setTimeout(decorate,2000);setTimeout(refreshSoul,400)}});

/* ---------- старт ---------- */
let started=false;
function start(){buildBar();
 const box=D.getElementById('messages');if(box&&!box.dataset.nx3){box.dataset.nx3='1';new MutationObserver(muts=>{const own=m=>{const t=m.target.nodeType===1?m.target:m.target.parentElement;if(t?.closest?.('footer.nx3-meta'))return true;const ns=[...m.addedNodes,...m.removedNodes];return m.type==='childList'&&ns.length>0&&ns.every(n=>n.nodeType===1&&n.matches?.('footer.nx3-meta'))};if(muts.every(own))return;schedule()}).observe(box,{childList:true,subtree:true,characterData:true})}
 if(!started){started=true;refreshSoul();decorate()}}
if(D.readyState!=='loading')start();else D.addEventListener('DOMContentLoaded',start);
setTimeout(start,1500);setTimeout(counter,2500);
W.NoxAI3={quote,getPrompt,setPrompt,history:hist,pushHistory:pushHist,refreshSoul,decorate,counter};
})();
