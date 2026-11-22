/* NOX web extras (web-исполнитель): планеты фона, режимы глубины с оценкой времени,
   нижнее меню-слайдер, панель «Что NOX вспомнил», микрофон (STT + silero VAD). Аддитивно, без правки чужих файлов. */
(function(){'use strict';
var D=document,L=localStorage,page=(location.pathname.split('/').pop()||'index.html');
function $(s,r){return (r||D).querySelector(s)}
function el(t,c,h){var e=D.createElement(t);if(c)e.className=c;if(h!=null)e.innerHTML=h;return e}
function jget(k,d){try{var v=JSON.parse(L.getItem(k));return v==null?d:v}catch(e){return d}}
var PLANETS=[['earth','Земля'],['mars','Марс'],['jupiter','Юпитер'],['saturn','Сатурн'],['venus','Венера'],['mercury','Меркурий'],['uranus','Уран'],['neptune','Нептун']];
var PURL='assets/nox-approved/planets/';
/* 1. планета фона */
function applyPlanet(){var p=L.getItem('nox.bg.planet'),b=$('#nxw-planet-bg');
 if(!p||p==='none'){if(b)b.remove();return}
 if(!b){b=el('div');b.id='nxw-planet-bg';D.body.prepend(b)}
 b.style.backgroundImage='url('+PURL+p+'.jpg)'}
function planetPicker(){var host=(page==='settings.html')?($('main')||D.body):null;if(!host||$('#nxw-planets'))return;
 var c=el('section','nxw-card');c.id='nxw-planets';c.innerHTML='<h3>Планета фона</h3>';
 var w=el('div','nxw-pl');var cur=L.getItem('nox.bg.planet')||'none';
 [['none','Нет']].concat(PLANETS).forEach(function(p){var b=el('button');b.type='button';b.title=p[1];
  b.style.backgroundImage=p[0]==='none'?'none':'url('+PURL+p[0]+'.jpg)';b.setAttribute('aria-pressed',String(cur===p[0]));b.innerHTML='<span>'+p[1]+'</span>';
  b.onclick=function(){L.setItem('nox.bg.planet',p[0]);[].forEach.call(w.children,function(x){x.setAttribute('aria-pressed','false')});b.setAttribute('aria-pressed','true');applyPlanet()};w.append(b)});
 c.append(w);host.append(c)}
/* 2. режимы глубины */
var DEP={low:['Быстро',150],auto:['Авто',320],high:['Глубоко',800],max:['Максимум',1800]};
function tps(){return Math.max(2,+L.getItem('nox.tps')||6)}
function fmt(s){return s<90?Math.round(s)+' с':Math.round(s/60)+' мин'}
function eta(k){var t=DEP[k][1]/tps();return '≈ '+fmt(t*.6)+'–'+fmt(t*1.5)}
function depthUI(){var g=$('.nxc-depth');if(!g)return;
 [].forEach.call(g.querySelectorAll('button[data-depth]'),function(b){var k=b.getAttribute('data-depth');if(!DEP[k])return;
  if(b.textContent!==DEP[k][0])b.textContent=DEP[k][0];b.title=DEP[k][0]+': '+eta(k)});
 var e=$('.nxw-eta');if(!e){e=el('span','nxw-eta');g.after(e)}
 var a=g.querySelector('[aria-pressed=true]');var k=a?a.getAttribute('data-depth'):'auto';e.textContent=eta(k)}
/* 3. нижнее меню-слайдер */
var NAV=[['chat.html','💬','Чат'],['resonance.html','🌌','Резонанс'],['memory.html','🧠','Память'],['training.html','🎓','Обучение'],['projects.html','🗂','Проекты'],['templates.html','🧩','Шаблоны'],['studio.html','🎨','Студия'],['cinema.html','🎬','Кино'],['widgets.html','🧱','Виджеты'],['dispatcher.html','🛰','Диспетчер'],['system.html','📊','Система'],['models.html','🤖','Модели'],['downloads.html','⬇','Загрузки'],['settings.html','⚙','Настройки']];
function bnav(){if($('#nxw-bnav'))return;var n=el('nav');n.id='nxw-bnav';n.setAttribute('aria-label','Нижнее меню');
 NAV.forEach(function(x){var a=el('a',x[0]===page?'on':'','<b>'+x[1]+'</b>'+x[2]);a.href=x[0];n.append(a)});D.body.append(n);
 var on=n.querySelector('.on');if(on)n.scrollLeft=on.offsetLeft-n.clientWidth/2+on.clientWidth/2}
/* 4. «Что NOX вспомнил»: серверная память /memory/api (s03), запасной вариант - localStorage */
var SF=[];
function mapi(o){return fetch('/memory/api',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(o)}).then(function(r){return r.json()})}
function pushFacts(list){var t=list.map(function(f){return f.text}).slice(0,25).join('\n');L.setItem('nox.facts.text',t);
 var c=jget('nox.newchat.cfg',{});if(c.facts!==t){c.facts=t;L.setItem('nox.newchat.cfg',JSON.stringify(c))}}
function loadFacts(){return mapi({op:'list',limit:40}).then(function(j){if(j.ok){SF=j.facts;pushFacts(SF)}return SF}).catch(function(){SF=(jget('nox.facts.v1',[])||[]).map(function(t,i){return {id:'l'+i,text:t,local:true}});return SF})}
function memPanel(){if(page!=='memory.html'||$('#nxw-facts'))return;var host=$('main')||D.body;
 var c=el('section','nxw-card');c.id='nxw-facts';c.innerHTML='<h3>Что NOX вспомнил <small id="nxw-src" style="opacity:.6"></small></h3><div id="nxw-fl"></div><p><button class="nxw-b" id="nxw-add">+ факт</button> <button class="nxw-b" id="nxw-q">Найти</button> <input id="nxw-qi" placeholder="запрос к памяти" style="background:#0003;color:#fff;border:1px solid #fff3;border-radius:8px;padding:3px 8px"></p>';
 host.prepend(c);var fl=$('#nxw-fl',c);
 function draw(list){fl.innerHTML='';var loc=list.length&&list[0].local;$('#nxw-src',c).textContent=loc?'(локально, сервер недоступен)':'(сервер, s03)';
  if(!list.length)fl.append(el('div','','<i>Пока пусто.</i>'));
  list.forEach(function(f){var r=el('div','nxw-fact');var d=el('div');d.contentEditable='true';d.textContent=f.text;
   d.onblur=function(){var t=d.textContent.trim();if(t===f.text)return;if(f.local){var a=jget('nox.facts.v1',[]);a[+f.id.slice(1)]=t;L.setItem('nox.facts.v1',JSON.stringify(a));return}
    mapi({op:'correct',id:f.id,text:t,reason:'правка в вебе'}).then(function(){f.text=t;pushFacts(SF)})};
   var x=el('button','nxw-b','✕');x.onclick=function(){if(f.local){var a=jget('nox.facts.v1',[]);a.splice(+f.id.slice(1),1);L.setItem('nox.facts.v1',JSON.stringify(a));return loadFacts().then(draw)}
    mapi({op:'delete',id:f.id,reason:'удалено в вебе'}).then(function(){return loadFacts()}).then(draw)};
   r.append(d,x);fl.append(r)})}
 loadFacts().then(draw);
 $('#nxw-add',c).onclick=function(){var t=prompt('Новый факт');if(!t)return;if(SF.length&&SF[0].local){var a=jget('nox.facts.v1',[]);a.push(t);L.setItem('nox.facts.v1',JSON.stringify(a));return loadFacts().then(draw)}mapi({op:'add',text:t}).then(function(){return loadFacts()}).then(draw)};
 $('#nxw-q',c).onclick=function(){var q=$('#nxw-qi',c).value.trim();if(!q)return loadFacts().then(draw);mapi({op:'search',query:q,k:10}).then(function(j){draw((j.hits||[]).map(function(h){return {id:h.ref,text:h.text||h.snippet||JSON.stringify(h).slice(0,200)}}))})}}
/* передача фактов в чат: nox_facts в тело запроса к шлюзу */
(function(){var of=window.fetch;window.fetch=function(u,o){try{if(o&&typeof o.body==='string'&&/\/glm\/|\/api\/chat/.test(String(u&&u.url||u))&&o.body.charAt(0)==='{'){var j=JSON.parse(o.body),t=L.getItem('nox.facts.text');if(t&&!j.nox_facts){j.nox_facts=t.split('\n').filter(Boolean);o=Object.assign({},o,{body:JSON.stringify(j)})}}}catch(e){}return of.call(this,u,o)}})();
/* 4b. «Шаблоны» в верхнем меню/на главной + встроенные канбан и календарь */
function tplLink(){if(page==='templates.html')return;var as=[].filter.call(D.querySelectorAll('a[href$="widgets.html"],a[href$="projects.html"]'),function(a){return !a.closest('#nxw-bnav')});
 as.forEach(function(a){var p=a.parentNode;if(!p||p.querySelector('a[href$="templates.html"]'))return;var c=a.cloneNode(true);c.href='templates.html';c.removeAttribute('aria-current');c.classList.remove('on','active');
  var w=D.createTreeWalker(c,NodeFilter.SHOW_TEXT),n,done=0;while(n=w.nextNode()){if(n.nodeValue.trim()){n.nodeValue=n.nodeValue.replace(/\S.*\S|\S/,'Шаблоны');done=1;break}}
  if(!done)c.append('Шаблоны');a.after(c)})}
function embeds(){var map={'projects.html':['kb','Канбан проектов'],'widgets.html':['cl','Календарь']},m=map[page];if(!m||$('#nxw-emb'))return;
 var c=el('section','nxw-card');c.id='nxw-emb';c.innerHTML='<h3>'+m[1]+'</h3><iframe loading="lazy" src="templates.html?embed=1#'+m[0]+'" style="width:100%;height:560px;border:0;border-radius:12px;background:transparent"></iframe>';(($('main'))||D.body).append(c)}
/* 5. микрофон: STT + silero VAD (конец реплики) */
function mic(){if(page!=='chat.html'&&page!=='resonance.html'||$('#nxw-mic')||$('[data-nox-mic]'))return;
 var SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR)return;
 var b=el('button',null,'🎙');b.id='nxw-mic';b.type='button';b.title='Голосовой ввод';D.body.append(b);
 var rec=null,vad=null,txt='';
 function target(){return $('textarea')||$('input[type=text]')}
 function stop(){if(rec){try{rec.stop()}catch(e){}}if(vad){try{vad.pause()}catch(e){}}b.classList.remove('rec')}
 function send(){var t=target();if(!t)return;t.value=txt.trim();t.dispatchEvent(new Event('input',{bubbles:true}));
  var f=t.closest('form');if(f&&f.requestSubmit)f.requestSubmit();else{var s=$('button[type=submit],.send,#send');if(s)s.click()}}
 function loadVad(){return new Promise(function(ok){if(window.vad)return ok(window.vad);
  var ort=el('script');ort.src='vendor/onnxruntime-web/dist/ort.min.js';ort.onload=function(){var s=el('script');s.src='vendor/vad-web/dist/bundle.min.js';s.onload=function(){ok(window.vad)};s.onerror=function(){ok(null)};D.head.append(s)};ort.onerror=function(){ok(null)};D.head.append(ort)})}
 b.onclick=function(){if(b.classList.contains('rec')){stop();send();return}
  txt='';rec=new SR();rec.lang='ru-RU';rec.interimResults=true;rec.continuous=true;
  rec.onresult=function(e){txt='';for(var i=0;i<e.results.length;i++)txt+=e.results[i][0].transcript;var t=target();if(t)t.value=txt};
  rec.onend=function(){b.classList.remove('rec')};rec.start();b.classList.add('rec');
  loadVad().then(function(v){if(!v||!v.MicVAD)return;return v.MicVAD.new({model:'v5',baseAssetPath:'vendor/vad-web/dist/',onnxWASMBasePath:'vendor/onnxruntime-web/dist/',onSpeechEnd:function(){setTimeout(function(){if(b.classList.contains('rec')){stop();send()}},400)}}).then(function(m){vad=m;m.start()})}).catch(function(){})}}
/* 6. лёгкость: ленивые изображения */
function lazy(){[].forEach.call(D.images,function(i){if(!i.loading)i.loading='lazy';i.decoding='async'})}
function init(){applyPlanet();planetPicker();bnav();memPanel();embeds();tplLink();setTimeout(tplLink,1500);setTimeout(tplLink,4000);if(page==='chat.html'||page==='resonance.html')loadFacts();mic();lazy();depthUI();
 new MutationObserver(function(){depthUI()}).observe(D.body,{childList:true,subtree:true,attributes:true,attributeFilter:['aria-pressed']})}
if(D.readyState==='loading')D.addEventListener('DOMContentLoaded',init);else init();
})();
