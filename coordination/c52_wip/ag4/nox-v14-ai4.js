/* NOX v14 · AI4 — действия над последним ответом: Уточни / Проще / Подробнее / Короче / Продолжить */
(function(){'use strict';
if(window.NOX_V14_AI4)return;window.NOX_V14_AI4=true;
var D=document,timer=0,stopped=false,obs=null;
var ACTS=[
 {act:'clarify',label:'Уточни',icon:'?',q:'Уточни, пожалуйста, последний ответ: что именно ты имел в виду и на чём это основано?'},
 {act:'simpler',label:'Проще',icon:'◇',q:'Объясни последний ответ проще: простыми словами, без жаргона, с коротким примером.'},
 {act:'deeper',label:'Подробнее',icon:'＋',q:'Раскрой последний ответ подробнее: добавь детали, шаги и обоснование.'},
 {act:'shorter',label:'Короче',icon:'－',q:'Сократи последний ответ до самого главного: 2–3 предложения, без потери смысла.'},
 {act:'continue',label:'Продолжить',icon:'▸',q:'Продолжи ответ ровно с того места, где он оборвался, без повторов.'}
];
function toast(t,k){try{window.NoxToast&&window.NoxToast(t,k||'info',2200)}catch(e){}}
function lastNox(){var a=D.querySelectorAll('#messages>.msg.nox');return a.length?a[a.length-1]:null}
function bodyText(m){var d=m&&m.querySelector(':scope>div');return ((d||m||{}).textContent||'').trim()}
function busy(){var s=D.querySelector('#chatForm [data-action="stop"]');return !!(s&&!s.disabled)}
function looksCut(t){
 if(!t)return false;
 if(stopped)return true;
 var f=(t.match(/```/g)||[]).length;if(f%2)return true;
 return !/[.!?…»")\]}:;。！？`*_|>\-]\s*$/.test(t)&&!/[\u{1F300}-\u{1FAFF}☀-➿]\s*$/u.test(t);
}
function send(text){
 if(!text)return false;
 if(busy()){toast('NOX ещё отвечает — дождитесь или нажмите STOP','warn');return false}
 var comp=D.querySelector('loquix-chat-composer');
 if(comp){var inp=comp.shadowRoot&&comp.shadowRoot.querySelector('loquix-prompt-input');if(inp)inp.value=text;
  comp.dispatchEvent(new CustomEvent('loquix-submit',{detail:{content:text},bubbles:true,composed:true}));return true}
 var p=D.getElementById('prompt'),f=D.getElementById('chatForm');if(!p||!f)return false;
 p.value=text;p.dispatchEvent(new Event('input',{bubbles:true}));
 if(f.requestSubmit)f.requestSubmit();else f.dispatchEvent(new Event('submit',{cancelable:true,bubbles:true}));
 return true;
}
function row(m){
 var r=m.querySelector('.nx-act-row');
 if(!r){r=D.createElement('div');r.className='nx-act-row';r.setAttribute('role','toolbar');r.setAttribute('aria-label','Действия с ответом');m.appendChild(r)}
 return r;
}
function build(){
 timer=0;var m=lastNox();
 D.querySelectorAll('#messages .nx-act-row').forEach(function(r){if(r.closest('.msg.nox')!==m){
  r.querySelectorAll('.nx-ai4').forEach(function(b){b.remove()});
  if(m){var nr=row(m);while(r.firstChild)nr.appendChild(r.firstChild)}r.remove()}});
 if(!m)return;
 var t=bodyText(m);if(!t)return;
 var r=row(m);
 ACTS.forEach(function(a){
  if(r.querySelector('[data-act="'+a.act+'"]'))return;
  var b=D.createElement('button');b.type='button';b.className='nx-act nx-ai4';b.dataset.act=a.act;b.title=a.q;
  b.innerHTML='<span class="nx-ai4-ic" aria-hidden="true"></span><span></span>';
  b.firstChild.textContent=a.icon;b.lastChild.textContent=a.label;
  b.addEventListener('click',function(e){e.preventDefault();e.stopPropagation();if(send(a.q))toast(a.label+' → NOX','info')});
  r.appendChild(b);
 });
 var c=r.querySelector('[data-act="continue"].nx-ai4');
 if(c){var cut=!busy()&&looksCut(t);c.classList.toggle('is-hot',cut);c.setAttribute('aria-label',cut?'Продолжить — ответ, похоже, оборван':'Продолжить')}
}
function schedule(){if(timer)clearTimeout(timer);timer=setTimeout(build,150)}
function init(){
 var box=D.getElementById('messages');if(!box)return;
 obs=new MutationObserver(function(list){
  for(var i=0;i<list.length;i++){var n=list[i].target;if(n.nodeType===1&&n.closest&&n.closest('.nx-act-row'))continue;
   if(list[i].type==='childList'&&Array.prototype.some.call(list[i].addedNodes,function(x){return x.nodeType===1&&x.classList.contains('msg')&&x.classList.contains('nox')&&!bodyText(x)}))stopped=false;
   schedule();return}
 });
 obs.observe(box,{childList:true,subtree:true,characterData:true});
 D.addEventListener('click',function(e){var s=e.target.closest&&e.target.closest('[data-action="stop"]');if(s&&!s.disabled){stopped=true;schedule()}},true);
 var stopBtn=D.querySelector('#chatForm [data-action="stop"]');
 if(stopBtn)new MutationObserver(schedule).observe(stopBtn,{attributes:true,attributeFilter:['disabled']});
 schedule();
}
window.NoxAI4={actions:ACTS.map(function(a){return {act:a.act,label:a.label,prompt:a.q}}),send:send,refresh:build,looksCut:looksCut,
 run:function(act){var a=ACTS.filter(function(x){return x.act===act})[0];return a?send(a.q):false}};
if(D.readyState==='loading')D.addEventListener('DOMContentLoaded',init);else init();
})();
