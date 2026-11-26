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
var dc=$('#chat');
var think=function(s){return s.replace(/<think>[\s\S]*?(<\/think>|$)/gi,'').replace(/^\s+/,'')};
function toast(t,ms){var e=$('#dcToast');e.textContent=t;e.hidden=false;clearTimeout(toast.t);toast.t=setTimeout(function(){e.hidden=true},ms||4000)}
window.NOXdcToast=toast;
function title(){$('#dcSub').textContent=cur.title&&cur.title!=='Новый диалог'?cur.title:'новый диалог'}
/* Deep Chat: оформление через токены Графита */
var V=function(n){return 'var('+n+')'};
dc.style.cssText='';
dc.chatStyle={backgroundColor:'transparent',border:'none',fontFamily:'inherit'};
dc.messageStyles={default:{shared:{bubble:{borderRadius:'12px',padding:'8px 12px',maxWidth:'92%',fontSize:'clamp(15px,0.35vw + 10px,18px)',lineHeight:'1.6'}},
 user:{bubble:{backgroundColor:V('--gx-4'),color:V('--gx-12'),border:'1px solid '+V('--gx-6')}},
 ai:{bubble:{backgroundColor:'transparent',color:V('--gx-12'),padding:'4px 4px'}}}};
dc.textInput={styles:{container:{backgroundColor:V('--gx-3'),border:'1px solid '+V('--gx-6'),borderRadius:'14px',margin:'0 8px 10px',padding:'2px 4px'},text:{color:V('--gx-12'),fontSize:'15px'}},placeholder:{text:'Напишите сообщение…',style:{color:V('--gx-10')}}};
dc.submitButtonStyles={submit:{container:{default:{backgroundColor:V('--gx-acc'),borderRadius:'8px',width:'32px',height:'32px'}},svg:{styles:{default:{filter:'brightness(0.15)'}}}}};
dc.auxiliaryStyle='::-webkit-scrollbar{width:8px}::-webkit-scrollbar-thumb{background:var(--gx-6,#363a3f);border-radius:4px}#messages{padding:12px 12px 4px}.dc-acts{display:flex;gap:6px;margin:4px 0 10px 22px;flex-wrap:wrap}.dc-acts button{height:28px;padding:0 10px;border-radius:8px;border:1px solid var(--gx-6,#363a3f);background:var(--nxb-bg,rgba(255,255,255,.055));color:var(--gx-11,#b0b4ba);font:inherit;font-size:12px;cursor:pointer}.dc-acts button:hover{background:var(--nxb-bg-h,rgba(255,255,255,.1));color:var(--gx-12,#edeef0)}.dc-via{margin:2px 0 0 22px;font-size:11px;color:var(--gx-10,#777b84)}.dc-k8{margin:2px 0 4px 22px;font-size:12px;color:var(--gx-10,#777b84)}.dc-k8 .k8-conf{height:3px;background:var(--gx-5,#2e3135);border-radius:2px;width:120px}.dc-k8 .k8-conf i{display:block;height:100%;background:var(--gx-acc,#9db1d1);border-radius:2px}.dc-k8 details{margin-top:2px}.dc-k8 ul{margin:4px 0;padding-left:18px}pre{background:var(--gx-2,#18191b)!important;border:1px solid var(--gx-6,#363a3f);border-radius:8px;padding:10px;overflow:auto}code{font-size:13px}';
dc.introMessage={text:'Привет! Я NOX. Спросите что угодно: отвечу, найду, напишу, посчитаю.'};
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
 var q=document.createElement('div');q.className='dc-q';
 [['Что умеешь','Кратко опиши, что ты умеешь делать на этом сервере.'],['План дня','Составь план работы на сегодня из моих текущих задач и спроси, чего не хватает.'],['Проверить голос','Объясни по шагам, как проверить, что голосовой ввод и озвучка работают.'],['Идеи','Придумай три идеи, как улучшить интерфейс Резонанса, и оцени каждую.']].forEach(function(x){var b=document.createElement('button');b.type='button';b.textContent=x[0];b.onclick=function(){dc.submitUserMessage({text:x[1]})};q.appendChild(b)});
 d.appendChild(q);inp.parentNode.insertBefore(d,inp);window.__dcQ=q;qvis()}
function qvis(){if(window.__dcQ)window.__dcQ.style.display=cur.msgs.length?'none':'flex'}
dc.auxiliaryStyle+='.dc-strip{position:absolute;left:0;right:0;bottom:66px;z-index:2;display:flex;gap:8px;align-items:center;flex-wrap:wrap;justify-content:center;padding:0 8px}#chat-view{position:relative}#messages{padding-bottom:48px!important}.dc-seg{display:inline-flex;border:1px solid var(--gx-6,#363a3f);border-radius:8px;overflow:hidden}.dc-seg button,.dc-q button{height:28px;padding:0 10px;border:0;background:transparent;color:var(--gx-11,#b0b4ba);font:inherit;font-size:12px;cursor:pointer}.dc-seg button.on{background:var(--gx-5,#2e3135);color:var(--gx-12,#edeef0)}.dc-q{display:flex;gap:6px;flex-wrap:wrap}.dc-q button{border:1px solid var(--gx-6,#363a3f);border-radius:8px}.dc-q button:hover,.dc-seg button:hover{background:var(--nxb-bg-h,rgba(255,255,255,.1));color:var(--gx-12,#edeef0)}';
dc.addEventListener&&dc.addEventListener('render',function(){strip()});
[400,1200,2500].forEach(function(t){setTimeout(strip,t)});
function actsFor(text,meta,via){
 var root=dc.shadowRoot;if(!root)return;
 var msgs=root.querySelectorAll('.outer-message-container');var last=msgs[msgs.length-1];if(!last)return;
 var old=root.querySelector('.dc-acts-live');if(old){var p=old.parentNode;old.remove();}
 var box=document.createElement('div');box.className='dc-acts dc-acts-live';
 function b(l,t,f){var x=document.createElement('button');x.type='button';x.textContent=l;x.title=t;x.addEventListener('click',f);box.appendChild(x);return x}
 b('Копировать','Копировать ответ',function(e){try{navigator.clipboard.writeText(text);toast('Скопировано',1500)}catch(x){}});
 b('Ещё раз','Перегенерировать ответ',function(){regen()});
 b('Озвучить','Прочитать вслух',function(){try{speechSynthesis.cancel();var u=new SpeechSynthesisUtterance(text);u.lang='ru-RU';speechSynthesis.speak(u)}catch(x){}});
 b('В блокнот','Сохранить в блокнот',function(e){if(window.NOXNote&&NOXNote.add){NOXNote.add(text);toast('Сохранено в блокнот',1800)}else toast('Блокнот недоступен')});
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
 cur.msgs.push({role:'user',content:text,ts:Date.now()});
 if(cur.title==='Новый диалог')cur.title=text.replace(/\s+/g,' ').slice(0,44);
 var am={role:'assistant',content:'',ts:Date.now()};
 var ctrl=new AbortController();busy={ctrl:ctrl,turn:null};
 var raw='',sent='',meta=null,done=null,opened=false;
 signals.stopClicked.listener=function(){var b=busy;if(!b)return;try{fetch('/api/turn/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({conversation_id:cur.id,turn_id:b.turn||undefined})}).catch(function(){})}catch(e){}setTimeout(function(){ctrl.abort()},1200)};
 var reqBody={conversation_id:cur.id,message:text,mode:'auto',length:'normal',source:'full'};
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
window.NOXdc={cur:function(){return cur},threads:function(){return threads}};
})();
