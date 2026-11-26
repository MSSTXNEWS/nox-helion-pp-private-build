/* U: студия роли (шаблон «Резонанс»): холст слева, инструменты снизу, узкий чат справа. Реестр ./roles.json (копия state/roles.json). Готовые библиотеки: CodeMirror 5 (vendor/codemirror), markdown-it (vendor/markdown-it). API NOXroleStudio. Идемпотентно. */
(function(){ if(window.NOXroleStudio)return; const API=window.NOXroleStudio={v:1};
 const root=document.getElementById('rsRoot'); if(!root)return;
 const qs=new URLSearchParams(location.search); let rid=qs.get('role')||'writer';
 const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
 const FALLBACK={default:'writer',roles:{writer:{title:'Писатель',icon:'pencil',system:'Ты профессиональный редактор. Отвечай готовым текстом.',placeholder:'Начните писать...',templates:[{id:'a',label:'Статья',prompt:'Напиши статью на тему: '}],tools:[{id:'cont',label:'Продолжить',icon:'sparkles',kind:'ai',primary:true,prompt:'Продолжи текст:\n'}]}}};
 let cfg=FALLBACK,role,cm,busy=false,md=null,lastAI='';
 const KEY=()=>'nox.rs.'+rid+'.doc', HK=()=>'nox.rs.'+rid+'.chat';
 function ic(n){return '<sl-icon library="tabler" name="'+esc(n)+'" aria-hidden="true"></sl-icon>'}
 function css(){ if(document.getElementById('rs-css'))return; const s=document.createElement('style');s.id='rs-css';s.textContent=`
#rsRoot{--rs-h:calc(100vh - var(--ds-head-h,60px) - var(--ds-dock-h,48px) - 40px);display:grid;grid-template-columns:minmax(0,1fr) 340px;grid-template-rows:minmax(320px,1fr) auto;gap:12px;height:max(520px,var(--rs-h));color:var(--gx-12,#edeef0)}
#rsRoot .rs-card{background:color-mix(in srgb,var(--gx-2,#111113) 92%,transparent);border:1px solid var(--gx-5,#2a2c30);border-radius:16px;min-height:0;overflow:hidden;position:relative}
#rs-cv{grid-column:1;grid-row:1;display:flex;flex-direction:column}
#rs-bar{display:flex;align-items:center;gap:12px;padding:10px 14px;border-bottom:1px solid var(--gx-5,#2a2c30);font-size:14px}
#rs-bar h1{font-size:16px;margin:0;font-weight:600;letter-spacing:.02em}
#rs-bar .rs-st{margin-left:auto;color:var(--gx-11,#b0b4ba);font-size:12px;display:flex;gap:10px;align-items:center}
#rs-ed{flex:1;min-height:0;position:relative}
#rs-ed .CodeMirror{height:100%;background:transparent;color:var(--gx-12,#edeef0);font:17px/1.7 var(--sans,system-ui);padding:12px 8px}
#rs-ed .CodeMirror-cursor{border-left-color:var(--gx-12,#edeef0)}
#rs-ed .CodeMirror-selected{background:rgba(157,177,209,.28)}
#rs-ed .CodeMirror-lines{max-width:760px;margin:0 auto}
#rs-ph{position:absolute;left:0;right:0;top:20px;text-align:center;color:var(--gx-10,#7b7f86);pointer-events:none;font-size:16px}
#rs-pv{position:absolute;inset:0;overflow:auto;padding:24px;background:var(--gx-2,#111113);display:none;font-size:17px;line-height:1.7}
#rs-pv>div{max-width:760px;margin:0 auto}#rs-pv h1,#rs-pv h2,#rs-pv h3{margin:.8em 0 .4em}#rs-pv blockquote{border-left:3px solid var(--gx-7,#43484e);margin:0;padding-left:14px;color:var(--gx-11,#b0b4ba)}
#rs-tools{grid-column:1;grid-row:2;display:flex;flex-wrap:wrap;gap:8px;padding:10px;align-items:center}
#rs-tools button,#rs-chat button,.rs-btn{min-height:44px;min-width:44px;padding:0 14px;border-radius:12px;border:1px solid var(--gx-6,#43484e);background:var(--gx-3,#18191b);color:var(--gx-12,#edeef0);font:600 14px var(--sans,system-ui);display:inline-flex;align-items:center;gap:8px;cursor:pointer;transition:transform .15s,background .15s}
#rs-tools button:hover,#rs-chat button:hover{background:var(--gx-4,#202225);transform:translateY(-1px)}
#rs-tools button:focus-visible,#rs-chat button:focus-visible,#rs-in:focus-visible{outline:2px solid #9db1d1;outline-offset:2px}
#rs-tools button.pri,#rs-chat button.pri{background:var(--gx-12,#edeef0);color:var(--gx-1,#111113);border:0}
#rs-tools .sep{width:1px;height:28px;background:var(--gx-6,#43484e);margin:0 4px}
#rs-chat{grid-column:2;grid-row:1/3;display:flex;flex-direction:column}
#rs-ch-h{padding:10px 14px;border-bottom:1px solid var(--gx-5,#2a2c30);display:flex;gap:8px;align-items:center;font-size:14px}
#rs-f{flex:1;min-height:0;overflow:auto;padding:12px;display:flex;flex-direction:column;gap:10px}
.rs-m{padding:10px 12px;border-radius:12px;background:var(--gx-3,#18191b);font-size:14px;line-height:1.5;white-space:pre-wrap;word-break:break-word}
.rs-m.me{background:color-mix(in srgb,#9db1d1 16%,var(--gx-3,#18191b));align-self:flex-end;max-width:92%}
.rs-m .rs-ins{margin-top:8px;min-height:44px}
.rs-empty{margin:auto;text-align:center;padding:18px;border:1px dashed var(--gx-6,#43484e);border-radius:14px;color:var(--gx-11,#b0b4ba);display:flex;flex-direction:column;gap:10px}
.rs-empty b{color:var(--gx-12,#edeef0);font-size:16px}
.rs-chips{display:flex;flex-wrap:wrap;gap:8px;justify-content:center}
#rs-i{padding:10px;display:flex;gap:8px;border-top:1px solid var(--gx-5,#2a2c30);align-items:flex-end}
#rs-in{flex:1;min-height:44px;max-height:140px;resize:none;border-radius:12px;border:1px solid var(--gx-6,#43484e);background:var(--gx-1,#0e0f11);color:var(--gx-12,#edeef0);padding:10px 12px;font:14px/1.4 var(--sans,system-ui)}
@media (max-width:800px){#rsRoot{grid-template-columns:1fr;grid-template-rows:auto auto auto;height:auto}#rs-cv{min-height:55vh}#rs-chat{grid-column:1;grid-row:3;min-height:380px}}
body[data-page=writer] #k4-fab{display:none !important}
@media (prefers-reduced-motion:reduce){#rsRoot *{transition:none!important;animation:none!important}}`;document.head.appendChild(s)}
 function load(src,kind){return new Promise((ok,no)=>{const e=document.createElement(kind==='css'?'link':'script');if(kind==='css'){e.rel='stylesheet';e.href=src}else e.src=src;e.onload=()=>ok();e.onerror=()=>no(new Error('load '+src));document.head.appendChild(e)})}
 function layout(){
  root.innerHTML='<section id="rs-cv" class="rs-card" aria-label="Полотно"><div id="rs-bar"><h1 id="rs-title"></h1><span class="rs-st"><span id="rs-wc">0 слов</span><span id="rs-sv">сохранено</span></span></div><div id="rs-ed"><textarea id="rs-ta" aria-label="Текст"></textarea><div id="rs-ph"></div><div id="rs-pv"><div id="rs-pvb"></div></div></div></section>'
  +'<nav id="rs-tools" class="rs-card" aria-label="Инструменты"></nav>'
  +'<aside id="rs-chat" class="rs-card" aria-label="Чат"><div id="rs-ch-h"><sl-icon library="tabler" name="message-circle" aria-hidden="true"></sl-icon><b id="rs-ch-t">Чат</b><select id="rs-role" aria-label="Роль" style="margin-left:auto;min-height:44px;border-radius:10px"></select></div><div id="rs-f" aria-live="polite"></div><form id="rs-i"><textarea id="rs-in" rows="1" aria-label="Сообщение" placeholder="Задача для роли..."></textarea><button type="submit" class="pri" id="rs-go" aria-label="Отправить">'+ic('send')+'</button></form></aside>';
 }
 const $=s=>root.querySelector(s);
 function counts(){const t=cm.getValue();const w=(t.trim().match(/\S+/g)||[]).length;$('#rs-wc').textContent=w+' '+(w%10===1&&w%100!==11?'слово':(w%10>=2&&w%10<=4&&(w%100<10||w%100>=20)?'слова':'слов'));$('#rs-ph').style.display=t?'none':'block'}
 let svT;function saveSoon(){$('#rs-sv').textContent='сохраняю...';clearTimeout(svT);svT=setTimeout(()=>{try{localStorage.setItem(KEY(),cm.getValue())}catch(e){}$('#rs-sv').textContent='сохранено'},600)}
 function tools(){const box=$('#rs-tools');box.innerHTML='';const T=role.tools||[];
  T.forEach((t,i)=>{ if(i>0&&T[i-1].kind!==t.kind){const s=document.createElement('span');s.className='sep';box.appendChild(s)}
   const b=document.createElement('button');b.type='button';b.dataset.id=t.id;if(t.primary)b.className='pri';b.innerHTML=ic(t.icon||'point')+'<span>'+esc(t.label)+'</span>';b.title=t.label;b.onclick=()=>run(t);box.appendChild(b)});
  const s=document.createElement('span');s.className='sep';box.appendChild(s);
  [['eye','Просмотр',()=>preview()],['copy','Копировать',()=>{navigator.clipboard&&navigator.clipboard.writeText(cm.getValue())}],['download','.md',()=>dl()]].forEach(a=>{const b=document.createElement('button');b.type='button';b.innerHTML=ic(a[0])+'<span>'+a[1]+'</span>';b.onclick=a[2];if(a[0]==='eye')b.id='rs-eye';box.appendChild(b)});}
 async function preview(){const pv=$('#rs-pv'),on=pv.style.display==='block';if(on){pv.style.display='none';return}
  if(!md){try{const M=await import('./vendor/markdown-it/markdown-it.esm.js');md=new (M.default||M)({html:false,breaks:true,linkify:true})}catch(e){md=null}}
  $('#rs-pvb').innerHTML=md?md.render(cm.getValue()):'<pre>'+esc(cm.getValue())+'</pre>';pv.style.display='block'}
 function dl(){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([cm.getValue()],{type:'text/markdown'}));a.download=rid+'.md';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),2000)}
 function fmt(t){const sel=cm.getSelection();if(t.wrap)cm.replaceSelection(t.wrap+(sel||'текст')+t.wrap);else{const c=cm.getCursor('from');cm.replaceRange(t.pre,{line:c.line,ch:0})}cm.focus()}
 function run(t){ if(t.kind==='fmt')return fmt(t); const sel=cm.getSelection();const body=sel||cm.getValue();
  if(!body.trim()){say('sys','Сначала напишите или выделите текст: инструмент «'+t.label+'» работает с ним.');cm.focus();return}
  ask(t.prompt+body,t.label,!!sel)}
 function feed(){return $('#rs-f')}
 function emptyState(){const f=feed();if(f.children.length)return;const d=document.createElement('div');d.className='rs-empty';d.innerHTML='<b>'+esc(role.title)+' на связи</b><span>Опишите задачу или выберите шаблон. Результат можно вставить прямо в текст.</span><div class="rs-chips"></div>';
  (role.templates||[]).forEach(t=>{const b=document.createElement('button');b.type='button';b.textContent=t.label;b.onclick=()=>{const i=$('#rs-in');i.value=t.prompt;i.focus()};d.querySelector('.rs-chips').appendChild(b)});f.appendChild(d)}
 function say(kind,text){const f=feed();const e=f.querySelector('.rs-empty');if(e)e.remove();const d=document.createElement('div');d.className='rs-m'+(kind==='me'?' me':'');d.textContent=text;f.appendChild(d);f.scrollTop=f.scrollHeight;return d}
 async function ask(prompt,label,hasSel){ if(busy)return;busy=true;const go=$('#rs-go');go.setAttribute('aria-busy','true');
  say('me',(label?label+': ':'')+prompt.slice(0,160)+(prompt.length>160?'...':''));const out=say('ai','');out.classList.add('u-skel');out.style.minHeight='44px';let acc='';
  try{ const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:'nox-helion:latest',stream:true,nox_mode:'fast',conversation_id:'role-'+rid,messages:[{role:'system',content:role.system||''},{role:'user',content:prompt}]})});
   if(!r.ok)throw new Error('HTTP '+r.status);const rd=r.body.getReader(),dec=new TextDecoder();let buf='';
   for(;;){const {done,value}=await rd.read();if(done)break;buf+=dec.decode(value,{stream:true});let i;while((i=buf.indexOf('\n'))>=0){const ln=buf.slice(0,i).trim();buf=buf.slice(i+1);if(!ln)continue;let o;try{o=JSON.parse(ln)}catch(x){continue}if(o.error)throw new Error(o.error);const c=(o.message&&o.message.content)||(typeof o.response==='string'?o.response:'');if(c){acc+=c;out.classList.remove('u-skel');out.textContent=acc;feed().scrollTop=feed().scrollHeight}}}
   if(!acc)throw new Error('пустой ответ');
   lastAI=acc;const b=document.createElement('button');b.type='button';b.className='rs-ins';b.innerHTML=ic('corner-down-left')+'<span>'+(hasSel?'Заменить выделенное':'Вставить в текст')+'</span>';b.onclick=()=>{hasSel&&cm.getSelection()?cm.replaceSelection(acc):cm.replaceRange((cm.getValue()?'\n\n':'')+acc,{line:cm.lastLine(),ch:1e9});cm.focus()};out.appendChild(document.createElement('br'));out.appendChild(b);
  }catch(e){out.classList.remove('u-skel');out.textContent='NOX недоступен: '+e.message+'. Повторите чуть позже.'}
  busy=false;go.removeAttribute('aria-busy')}
 function roleSel(){const s=$('#rs-role');s.innerHTML='';Object.keys(cfg.roles).forEach(k=>{const r=cfg.roles[k];const o=document.createElement('option');o.value=k;o.textContent=r.title+(r.soon?' (скоро)':'');if(r.soon)o.disabled=true;if(k===rid)o.selected=true;s.appendChild(o)});s.onchange=()=>{location.search='?role='+s.value}}
 async function init(){ css();
  try{const r=await fetch('./roles.json?v='+Date.now());if(r.ok)cfg=await r.json()}catch(e){}
  if(!cfg.roles[rid]||cfg.roles[rid].soon)rid=cfg.default||'writer';role=cfg.roles[rid]||FALLBACK.roles.writer;
  layout();document.title='NOX HELION · '+role.title.toUpperCase();$('#rs-title').textContent=role.title;$('#rs-ph').textContent=role.placeholder||'';$('#rs-ch-t').textContent='Чат: '+role.title;roleSel();
  try{await load('./vendor/codemirror/codemirror.css','css');await load('./vendor/codemirror/codemirror.iife.js')}catch(e){}
  const CM=window.NOX_codemirror&&(window.NOX_codemirror.default||window.NOX_codemirror);
  if(CM&&CM.fromTextArea){cm=CM.fromTextArea($('#rs-ta'),{lineWrapping:true,viewportMargin:Infinity})}
  else{const ta=$('#rs-ta');ta.style.cssText='width:100%;height:100%;background:transparent;color:inherit;border:0;padding:16px;font:17px/1.7 system-ui';cm={getValue:()=>ta.value,setValue:v=>{ta.value=v},getSelection:()=>ta.value.substring(ta.selectionStart,ta.selectionEnd),replaceSelection:s=>{ta.setRangeText(s,ta.selectionStart,ta.selectionEnd,'end');ta.dispatchEvent(new Event('input'))},replaceRange:(s)=>{ta.value+=s;ta.dispatchEvent(new Event('input'))},getCursor:()=>({line:0,ch:0}),lastLine:()=>0,focus:()=>ta.focus(),on:(e,f)=>ta.addEventListener('input',f)}}
  try{cm.setValue(localStorage.getItem(KEY())||'')}catch(e){}
  cm.on('change',()=>{counts();saveSoon()});counts();tools();emptyState();
  $('#rs-i').onsubmit=e=>{e.preventDefault();const i=$('#rs-in'),v=i.value.trim();if(!v)return;i.value='';const ctx=cm.getValue().trim();ask(ctx?v+'\n\nТекущий текст:\n'+ctx.slice(-4000):v,'',false)};
  $('#rs-in').addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();$('#rs-i').requestSubmit()}});
  API.cm=cm;API.ask=ask;API.role=role;
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
