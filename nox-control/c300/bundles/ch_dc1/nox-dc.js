/* NOX · чат на готовом Deep Chat (веб-компонент). Адаптер: /api/turn (NDJSON), история в nox.wow.threads, NOXNote, K8meta. */
(function(){
'use strict';
var $=function(s){return document.querySelector(s)},LS={g:function(k,d){try{var v=localStorage.getItem(k);return v==null?d:v}catch(e){return d}},s:function(k,v){try{localStorage.setItem(k,v)}catch(e){}}};
var uid=function(){return crypto.randomUUID?crypto.randomUUID():'c'+Date.now().toString(36)+Math.random().toString(36).slice(2,10)};
var threads=[];try{threads=JSON.parse(LS.g('nox.wow.threads','[]')).filter(function(t){return t&&Array.isArray(t.msgs)})}catch(e){}
var cur=null;
function save(){LS.s('nox.wow.threads',JSON.stringify(threads.slice(0,40).map(function(t){return Object.assign({},t,{msgs:t.msgs.slice(-80)})})));LS.s('nox.wow.cur',cur?cur.id:'')}
function pick(){var id=LS.g('nox.wow.cur','');cur=threads.find(function(t){return t.id===id})||null;if(!cur){cur={id:id||uid(),title:'Новый диалог',ts:Date.now(),msgs:[],srv:false};threads.unshift(cur)}}
pick();
var dc=$('#chat');var MINI=/[?&]mini=1/.test(location.search);var CTX=decodeURIComponent((location.search.match(/[?&]ctx=([^&]*)/)||[])[1]||'');if(MINI)document.body.classList.add('dc-mini');
var think=function(s){return s.replace(/<think>[\s\S]*?(<\/think>|$)/gi,'').replace(/^\s+/,'')};
function toast(t,ms){var e=$('#dcToast');e.textContent=t;e.hidden=false;clearTimeout(toast.t);toast.t=setTimeout(function(){e.hidden=true},ms||4000)}
window.NOXdcToast=toast;
function title(){$('#dcSub').textContent=cur.title&&cur.title!=='Новый диалог'?cur.title:'новый диалог'}
/* Deep Chat: оформление через токены Графита */
var V=function(n){return 'var('+n+')'};
dc.style.cssText='';
dc.chatStyle={backgroundColor:'transparent',border:'none',fontFamily:'inherit'};
dc.messageStyles={default:{shared:{bubble:{borderRadius:'12px',padding:'8px 12px',maxWidth:'92%',fontSize:'clamp(16px,0.25vw + 15px,19px)',lineHeight:'1.65'}},
 user:{bubble:{backgroundColor:V('--gx-4'),color:V('--gx-12'),border:'1px solid '+V('--gx-6')}},
 ai:{bubble:{backgroundColor:'transparent',color:V('--gx-12'),padding:'4px 4px'}}}};
dc.textInput={styles:{container:{backgroundColor:'color-mix(in srgb, var(--gx-3,#212225) 62%, transparent)',border:'1px solid rgba(255,255,255,.1)',borderRadius:'14px',backdropFilter:'blur(16px) saturate(1.3)',webkitBackdropFilter:'blur(16px) saturate(1.3)',margin:'0 8px 10px',padding:'2px 4px'},text:{color:V('--gx-12'),fontSize:'15px'}},placeholder:{text:'Напишите сообщение…',style:{color:V('--gx-10')}}};
dc.submitButtonStyles={submit:{container:{default:{backgroundColor:V('--gx-acc'),borderRadius:'8px',width:'32px',height:'32px'}},svg:{styles:{default:{filter:'brightness(0.15)'}}}}};
dc.auxiliaryStyle='::-webkit-scrollbar{width:8px}::-webkit-scrollbar-thumb{background:var(--gx-6,#363a3f);border-radius:4px}#messages{padding:16px 16px 8px}.dc-acts{display:flex;gap:8px;margin:8px 0 16px 22px;flex-wrap:wrap}.dc-acts button{width:32px;height:32px;padding:0;display:inline-grid;place-items:center;border-radius:8px;border:1px solid var(--gx-6,#363a3f);background:var(--nxb-bg,rgba(255,255,255,.055));color:var(--gx-11,#b0b4ba);font:inherit;font-size:12px;cursor:pointer}.dc-acts button:hover{background:var(--nxb-bg-h,rgba(255,255,255,.1));color:var(--gx-12,#edeef0)}.dc-via{margin:2px 0 0 22px;font-size:11px;color:var(--gx-10,#777b84)}.dc-k8{margin:2px 0 4px 22px;font-size:12px;color:var(--gx-10,#777b84)}.dc-k8 .k8-conf{height:3px;background:var(--gx-5,#2e3135);border-radius:2px;width:120px}.dc-k8 .k8-conf i{display:block;height:100%;background:var(--gx-acc,#9db1d1);border-radius:2px}.dc-k8 details{margin-top:2px}.dc-k8 ul{margin:4px 0;padding-left:18px}pre{background:var(--gx-2,#18191b)!important;border:1px solid var(--gx-6,#363a3f);border-radius:8px;padding:10px;overflow:auto}code{font-size:13px}';
var QS=['Что умеешь','Кратко опиши, что ты умеешь делать на этом сервере.','План дня','Составь план работы на сегодня из моих текущих задач и спроси, чего не хватает.','Проверить голос','Объясни по шагам, как проверить, что голосовой ввод и озвучка работают.','Идеи','Придумай три идеи, как улучшить интерфейс Резонанса, и оцени каждую.'];
var QH='<div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px">';for(var qi=0;qi<QS.length;qi+=2)QH+='<button class="deep-chat-suggestion-button" style="height:28px;padding:0 10px;border-radius:8px;border:1px solid var(--gx-6,#363a3f);background:transparent;color:var(--gx-11,#b0b4ba);font:inherit;font-size:12px;cursor:pointer">'+QS[qi]+'</button>';QH+='</div>';
dc.introMessage={html:'<div>Привет! Я NOX. Спросите что угодно: отвечу, найду, напишу, посчитаю.</div>'+QH};
dc.demo=false;
dc.stream=true;
dc.textInput.disabled=false;

dc.history=cur.msgs.map(function(m){return m.role==='user'?{role:'user',text:m.content}:{role:'ai',text:m.content}});
dc.attachmentContainerStyle={backgroundColor:V('--gx-3')};
var busy=null;
function cfgG(){try{return JSON.parse(LS.g('nox.wow.cfg','{}'))||{}}catch(e){return {}}}
function cfgS(k,v){var c=cfgG();c[k]=v;LS.s('nox.wow.cfg',JSON.stringify(c))}
dc.mixedFiles=true;dc.dragAndDrop=true;
dc.speechToText={webSpeech:{language:'ru-RU'},button:{position:'inside-right'}};
function b64(f){return new Promise(function(ok,no){var r=new FileReader();r.onload=function(){ok(String(r.result).split(',')[1]||'')};r.onerror=no;r.readAsDataURL(f)})}
function J(r){return r.json().then(function(j){if(!r.ok||j.ok===false)throw new Error(j.error||'HTTP '+r.status);return j})}
async function upBig(f){var i=await J(await fetch('/api/upload/init',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:f.name,size:f.size,mime:f.type||''})}));var CH=i.chunk||8388608,off=i.received||0;
 while(off<f.size){var j=await J(await fetch('/api/upload/chunk?id='+i.id+'&offset='+off,{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:f.slice(off,off+CH)}));off=j.received}
 var fin=await J(await fetch('/api/upload/finish',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:i.id})}));return {id:i.id,name:fin.name||f.name}}
async function upload(f){toast('Загружаю '+f.name+'…',60000);
 try{if(f.size>6e6){var r=await upBig(f);toast('Принят: '+r.name,2500);return r}
  var j=await (await fetch('/api/upload',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:f.name,b64:await b64(f),mime:f.type})})).json();
  if(!j.accepted)throw new Error(j.error||'не принят');toast('Принят: '+j.receipt.name,2500);return j.receipt}catch(e){toast('Не загрузился: '+f.name+' ('+(e.message||e)+')',5000);return null}}
function strip(){var root=dc.shadowRoot;if(!root||root.querySelector('.dc-strip'))return;var inp=root.querySelector('#input');if(!inp)return;
 var d=document.createElement('div');d.className='dc-strip';
 var m=cfgG().mode||'auto';
 var seg=document.createElement('div');seg.className='dc-seg';
 [['auto','Авто'],['fast','Быстро'],['deep','Глубоко']].forEach(function(x){var b=document.createElement('button');b.type='button';b.textContent=x[1];b.dataset.m=x[0];if(x[0]===m)b.className='on';b.onclick=function(){cfgS('mode',x[0]);seg.querySelectorAll('button').forEach(function(y){y.className=y===b?'on':''})};seg.appendChild(b)});
 d.appendChild(seg);

 inp.parentNode.insertBefore(d,inp);}
function qvis(){}
dc.auxiliaryStyle+='.dc-ghost{position:absolute;inset:0;padding:inherit;pointer-events:none;white-space:pre-wrap;overflow:hidden;color:var(--gx-9,#696e77);font:inherit;font-size:inherit;line-height:inherit}.dc-reply{display:flex;align-items:center;gap:8px;margin:0 10px 4px;padding:4px 10px;border-left:2px solid var(--gx-acc,#9db1d1);border-radius:6px;background:color-mix(in srgb,var(--gx-3,#212225) 60%,transparent);color:var(--gx-11,#b0b4ba);font-size:12px}.dc-reply span{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.dc-reply button{border:0;background:transparent;color:inherit;font-size:16px;cursor:pointer}@media(max-width:640px){.dc-strip{display:none!important}}.dc-strip{position:absolute;left:0;right:0;bottom:66px;z-index:2;display:flex;gap:8px;align-items:center;flex-wrap:wrap;justify-content:center;padding:0 8px}#chat-view{position:relative}#messages{padding-bottom:48px!important}.dc-seg{display:inline-flex;border:1px solid var(--gx-6,#363a3f);border-radius:8px;overflow:hidden}.dc-seg button,.dc-q button{height:28px;padding:0 10px;border:0;background:transparent;color:var(--gx-11,#b0b4ba);font:inherit;font-size:12px;cursor:pointer}.dc-seg button.on{background:var(--gx-5,#2e3135);color:var(--gx-12,#edeef0)}.dc-q{display:flex;gap:6px;flex-wrap:wrap}.dc-q button{border:1px solid var(--gx-6,#363a3f);border-radius:8px}.dc-q button:hover,.dc-seg button:hover{background:var(--nxb-bg-h,rgba(255,255,255,.1));color:var(--gx-12,#edeef0)}';
dc.addEventListener&&dc.addEventListener('render',function(){strip()});
function lab(){var r=dc.shadowRoot;if(!r)return;r.querySelectorAll('input:not([aria-label]),textarea:not([aria-label])').forEach(function(e){e.setAttribute('aria-label',e.type==='file'?'Выбрать файл':'Поле ввода')});var ti=r.querySelector('#text-input');if(ti&&!ti.getAttribute('aria-label'))ti.setAttribute('aria-label','Сообщение для NOX');
 r.querySelectorAll('#input button,#input [role=button],#input .input-button').forEach(function(e){if(e.getAttribute('aria-label'))return;var h=((e.id||'')+' '+(e.className&&e.className.baseVal!==undefined?e.className.baseVal:e.className)+' '+(e.innerHTML||'').slice(0,120)).toLowerCase();e.setAttribute('aria-label',/mic|speech|record/.test(h)?'Голосовой ввод':/submit|send/.test(h)?'Отправить':'Прикрепить файл');if(!e.getAttribute('role')&&e.tagName!=='BUTTON')e.setAttribute('role','button')})}
[400,1200,2500].forEach(function(t){setTimeout(function(){strip();lab()},t)});setInterval(lab,2500);
function actsFor(text,meta,via){
 var root=dc.shadowRoot;if(!root)return;
 var msgs=root.querySelectorAll('.outer-message-container');var last=msgs[msgs.length-1];if(!last)return;
 var old=root.querySelector('.dc-acts-live');if(old){var p=old.parentNode;old.remove();}
 var box=document.createElement('div');box.className='dc-acts dc-acts-live';
 var IC={copy:'<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h8"/>',re:'<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>',vol:'<path d="M11 5 6 9H3v6h3l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/>',note:'<path d="M6 3h12v18l-6-4-6 4z"/>',quote:'<path d="M7 17c-2 0-3-1.3-3-3.2C4 11 6 8 9 7M17 17c-2 0-3-1.3-3-3.2 0-2.8 2-5.8 5-6.8"/>',reply:'<path d="M9 7 4 12l5 5"/><path d="M4 12h10a6 6 0 0 1 6 6v1"/>',up:'<path d="M7 11v9H4v-9zM7 11l4-8a2 2 0 0 1 2 2l-1 4h6a2 2 0 0 1 2 2l-1.5 6A2 2 0 0 1 16.600 20H7"/>',down:'<path d="M17 13V4h3v9zM17 13l-4 8a2 2 0 0 1-2-2l1-4H6a2 2 0 0 1-2-2l1.500-6A2 2 0 0 1 7.400 4H17"/>'};
 function b(l,t,f){var x=document.createElement('button');x.type='button';var k=({'Копировать':'copy','Ещё раз':'re','Озвучить':'vol','В блокнот':'note','Цитата':'quote','Ответить':'reply','Нравится':'up','Не то':'down'})[l];x.title=t;x.setAttribute('aria-label',t);x.innerHTML='<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+IC[k]+'</svg>';x.addEventListener('click',f);box.appendChild(x);return x}
 b('Копировать','Копировать ответ',function(e){try{navigator.clipboard.writeText(text);toast('Скопировано',1500)}catch(x){}});
 b('Ещё раз','Перегенерировать ответ',function(){regen()});
 b('Озвучить','Прочитать вслух',function(){try{speechSynthesis.cancel();var u=new SpeechSynthesisUtterance(text);u.lang='ru-RU';speechSynthesis.speak(u)}catch(x){}});
 b('В блокнот','Сохранить в блокнот',function(e){if(window.NOXNote&&NOXNote.add){NOXNote.add(text);toast('Сохранено в блокнот',1800)}else toast('Блокнот недоступен')});
 b('Цитата','Ответить с цитатой',function(){var r=dc.shadowRoot,ti=r&&r.querySelector('#text-input');if(!ti)return;ti.textContent='> '+text.replace(/\s+/g,' ').slice(0,200)+'\n\n';ti.focus();try{var g=document.createRange();g.selectNodeContents(ti);g.collapse(false);var sl=r.getSelection?r.getSelection():getSelection();sl.removeAllRanges();sl.addRange(g)}catch(e){}});
 b('Ответить','Ответить на это сообщение',function(){setReply(text)});
 b('Нравится','Хороший ответ',function(e){e.target.style.color='var(--gx-ok,#6cc59a)'});
 b('Не то','Плохой ответ',function(e){e.target.style.color='var(--gx-bad,#e5736b)'});
 last.appendChild(box);
 if(via){var v=document.createElement('div');v.className='dc-via';v.textContent=via;last.appendChild(v)}
 if(meta&&window.K8meta){var k=document.createElement('div');k.className='dc-k8';if(K8meta.render(k,meta))last.appendChild(k)}
}
function regen(){
 if(busy)return;var i=cur.msgs.length-1;if(i<0)return;
 if(cur.msgs[i].role!=='user')cur.msgs.pop();
 var last=cur.msgs[cur.msgs.length-1];if(!last)return;cur.msgs.pop();save();
 dc.clearMessages(true);cur.msgs.forEach(function(m){dc.addMessage({role:m.role==='user'?'user':'ai',text:m.content})});
 dc.submitUserMessage({text:last.content});
}
dc.connect={stream:true,handler:function(body,signals){
 var msgs=body&&body.messages||[];var last=msgs[msgs.length-1];var text=last&&(last.text||last.content)||'';
 var files=(body&&body.files)||[];
 if(!text&&!files.length){signals.onResponse({error:'Пустое сообщение'});return}
 if(!text)text='(вложение)';
 var rq=replyTo;if(rq){text='↩ «'+rq+'»\n'+text;setReply(null)}
 cur.msgs.push({role:'user',content:text,ts:Date.now()});
 if(cur.title==='Новый диалог')cur.title=text.replace(/\s+/g,' ').slice(0,44);
 var am={role:'assistant',content:'',ts:Date.now()};
 var ctrl=new AbortController();busy={ctrl:ctrl,turn:null};
 var raw='',sent='',meta=null,done=null,opened=false;
 signals.stopClicked.listener=function(){var b=busy;if(!b)return;try{fetch('/api/turn/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({conversation_id:cur.id,turn_id:b.turn||undefined})}).catch(function(){})}catch(e){}setTimeout(function(){ctrl.abort()},1200)};
 var reqBody={conversation_id:cur.id,message:(MINI&&CTX?'[Пользователь сейчас на странице «'+CTX+'»]\n':'')+text,mode:'auto',length:'normal',source:'full'};
 if(!cur.srv)reqBody.seed=cur.msgs.slice(0,-1).slice(-20).map(function(m){return{role:m.role,content:m.content}});
 signals.onOpen();opened=true;qvis();
 Promise.all(files.map(upload)).then(function(rs){var at=rs.filter(Boolean).map(function(r){return{id:r.id}});if(at.length)reqBody.attachments=at;reqBody.mode=cfgG().mode||'auto';
 return fetch('/api/turn',{method:'POST',headers:{'Content-Type':'application/json'},signal:ctrl.signal,body:JSON.stringify(reqBody)})}).then(function(r){
  if(!r.ok)throw new Error('HTTP '+r.status);
  var rd=r.body.getReader(),dec=new TextDecoder(),buf='';
  function pump(){return rd.read().then(function(x){
   if(x.done)return;buf+=dec.decode(x.value,{stream:true});var k;
   while((k=buf.indexOf('\n'))>=0){var line=buf.slice(0,k).trim();buf=buf.slice(k+1);if(!line)continue;var f;try{f=JSON.parse(line)}catch(e){continue}
    if(f.t==='meta'){if(f.turn_id)busy.turn=f.turn_id;try{window.K8meta&&K8meta.handle(f)}catch(e){};if(f.meta)meta=f.meta}
    else if(f.t==='delta'&&f.text){raw+=f.text;var vis=think(raw);if(vis.length>sent.length){signals.onResponse({text:vis.slice(sent.length)});sent=vis}}
    else if(f.t==='error'){done=done||{};done.err=f.error;if(f.partial&&!raw)raw=f.partial}
    else if(f.t==='done'){done=Object.assign(done||{},f);if(f.meta)meta=f.meta;try{window.K8meta&&K8meta.handle(f)}catch(e){}}}
   return pump()})}
  return pump();
 }).catch(function(e){if(!ctrl.signal.aborted)done=Object.assign(done||{},{err:String(e.message||e)})}).then(function(){
  var vis=think(raw);
  if(!vis&&!(done&&done.err)){signals.onResponse({text:'(пустой ответ)'});vis='(пустой ответ)'}
  if(done&&done.err){signals.onResponse({text:(vis?'\n\n':'')+'Ошибка: '+done.err});}
  signals.onClose();
  am.content=vis;cur.msgs.push(am);cur.srv=!(done&&done.err&&!vis);save();title();
  var via=done&&done.level?('уровень: '+({glm:'GLM',nox:'NOX',fast:'быстрый'}[done.level]||done.level)):'';
  setTimeout(function(){actsFor(vis,meta,via)},120);
  busy=null;
  try{document.dispatchEvent(new CustomEvent('nox:reply-done',{detail:{text:vis.slice(0,140)}}))}catch(e){}
 });
}};

/* ответ на сообщение: превью над полем */
var replyTo=null;
function setInput(t){var r=dc.shadowRoot,ti=r&&r.querySelector('#text-input');if(!ti)return;ti.textContent=t;ti.focus();try{var g=document.createRange();g.selectNodeContents(ti);g.collapse(false);var sl=r.getSelection?r.getSelection():getSelection();sl.removeAllRanges();sl.addRange(g)}catch(e){}ti.dispatchEvent(new Event('input',{bubbles:true}))}
function setReply(t){replyTo=t?String(t).replace(/\s+/g,' ').slice(0,140):null;var r=dc.shadowRoot;if(!r)return;var o=r.querySelector('.dc-reply');if(o)o.remove();if(!replyTo)return;var d=document.createElement('div');d.className='dc-reply';var i=document.createElement('span');i.textContent='↩ '+replyTo;var x=document.createElement('button');x.type='button';x.textContent='×';x.setAttribute('aria-label','Отменить ответ');x.onclick=function(){setReply(null)};d.appendChild(i);d.appendChild(x);var inp=r.querySelector('#input');inp.parentNode.insertBefore(d,inp);var ti=r.querySelector('#text-input');ti&&ti.focus()}
window.NOXdcSetInput=setInput;window.NOXdcReply=setReply;
/* серый черновик (Tab - принять): /api/chat nox_mode fast, лимит 30 токенов */
var gh={t:null,ctl:null,txt:''};
function ghost(){var r=dc.shadowRoot;if(!r)return;var ti=r.querySelector('#text-input'),box=r.querySelector('#text-input-container');if(!ti||!box||box.querySelector('.dc-ghost'))return;
 box.style.position='relative';var g=document.createElement('div');g.className='dc-ghost';g.setAttribute('aria-hidden','true');box.appendChild(g);var cs=getComputedStyle(ti);g.style.cssText='position:absolute;left:'+ti.offsetLeft+'px;top:'+ti.offsetTop+'px;width:'+ti.offsetWidth+'px;height:'+ti.offsetHeight+'px;padding:'+cs.padding+';font:'+cs.font+';line-height:'+cs.lineHeight;
 function clear(){g.textContent='';gh.txt='';if(gh.ctl)try{gh.ctl.abort()}catch(e){}}
 function show(typed,sug){g.textContent='';var a=document.createElement('span');a.style.visibility='hidden';a.textContent=typed;var b=document.createElement('span');b.textContent=sug;g.appendChild(a);g.appendChild(b);gh.txt=sug}
 ti.addEventListener('input',function(){clear();clearTimeout(gh.t);var v=ti.innerText.replace(/\n$/,'');if(v.length<6||busy||/^[>\/]/.test(v))return;gh.t=setTimeout(function(){gh.ctl=new AbortController();var acc='';
  fetch('/api/chat',{method:'POST',signal:gh.ctl.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({model:'nox-helion:latest',stream:true,nox_mode:'fast',conversation_id:'qa-draft',options:{num_predict:30},messages:[{role:'user',content:'Продолжи текст пользователя одной короткой фразой (до 12 слов). Выведи ТОЛЬКО продолжение, без кавычек и пояснений. Текст: '+v}]})}).then(function(rs){var rd=rs.body.getReader(),dec=new TextDecoder(),buf='';
   function pump(){return rd.read().then(function(x){if(x.done)return;buf+=dec.decode(x.value,{stream:true});var k;while((k=buf.indexOf('\n'))>=0){var ln=buf.slice(0,k).trim();buf=buf.slice(k+1);if(!ln)continue;try{var o=JSON.parse(ln);var c=(o.message&&o.message.content)||(typeof o.response==='string'?o.response:'');if(c){acc+=c;if(ti.innerText.replace(/\n$/,'')===v)show(v,(/\s$/.test(v)||/^[\s,.!?;:]/.test(acc)?'':' ')+acc.replace(/^["«\s]+/,'').slice(0,160))}}catch(e){}}return pump()})}
   return pump()}).catch(function(){})},700)});
 ti.addEventListener('keydown',function(e){if(e.key==='Tab'&&gh.txt){e.preventDefault();var t=ti.innerText.replace(/\n$/,'')+gh.txt;clear();setInput(t)}else if(e.key==='Escape'||e.key==='Enter')clear()})}
[600,1500,3000].forEach(function(t){setTimeout(ghost,t)});

/* история */
function renderThr(){var h=$('#dcThrIn');h.textContent='';threads.forEach(function(t){if(!t.msgs.length&&t!==cur)return;var b=document.createElement('button');b.type='button';b.textContent=t.title||'Диалог';if(t===cur)b.className='on';b.onclick=function(){LS.s('nox.wow.cur',t.id);location.reload()};h.appendChild(b)})}
$('#dcNew').onclick=function(){if(busy)return;var t={id:uid(),title:'Новый диалог',ts:Date.now(),msgs:[],srv:false};threads.unshift(t);LS.s('nox.wow.threads',JSON.stringify(threads.slice(0,40)));LS.s('nox.wow.cur',t.id);location.reload()};
$('#dcThreads').onclick=function(){var a=$('#dcThr');renderThr();a.hidden=!a.hidden};
document.addEventListener('click',function(e){var a=$('#dcThr');if(!a.hidden&&!e.target.closest('#dcThr,#dcThreads'))a.hidden=true});
$('#dcPad').onclick=function(){if(window.NOXNote)NOXNote.toggle();else toast('Блокнот загружается…')};
title();
if(cur.msgs.length&&cur.msgs[cur.msgs.length-1].role!=='user')setTimeout(function(){actsFor(cur.msgs[cur.msgs.length-1].content,null,'')},700);
/* NOX пишет первым: тост, без перекрытия ленты */
function first(){var t=$('#dcFirst');if(t)return;fetch('/api/nox/outbox').then(function(r){return r.ok?r.json():null}).then(function(j){var m=j&&(j.messages||[])[0];if(!m||$('#dcFirst'))return;
 var e=document.createElement('div');e.id='dcFirst';e.className='dc-toast dc-first';var tm=new Date((m.ts||0)*1000).toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'});
 var h=document.createElement('b');h.textContent='NOX пишет первым · '+tm;var p=document.createElement('div');p.textContent=m.text;var r=document.createElement('div');r.className='dc-fa';
 function seen(a){fetch('/api/nox/outbox/seen',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:m.id,action:a})}).catch(function(){});e.remove()}
 [['Ответить','reply'],['Скрыть','hide']].forEach(function(x){var b=document.createElement('button');b.type='button';b.className='dc-b';b.textContent=x[0];b.onclick=function(){seen(x[1]);if(x[1]==='reply')dc.submitUserMessage({text:'> '+m.text.split('\n').join('\n> ')+'\n\n'})};r.appendChild(b)});
 e.appendChild(h);e.appendChild(p);e.appendChild(r);document.body.appendChild(e)}).catch(function(){})}
setTimeout(first,4000);setInterval(first,60000);
window.NOXdc={cur:function(){return cur},threads:function(){return threads},save:save,regen:regen,setInput:setInput,lastAi:function(){for(var i=cur.msgs.length-1;i>=0;i--)if(cur.msgs[i].role!=='user')return cur.msgs[i].content;return ''},submit:function(t){dc.submitUserMessage({text:t})}};
})();
