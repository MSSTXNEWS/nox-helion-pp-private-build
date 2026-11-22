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
/* 4. «Что NOX вспомнил» */
function facts(){return jget('nox.facts.v1',[])}
function memPanel(){if(page!=='memory.html'||$('#nxw-facts'))return;var host=$('main')||D.body;
 var c=el('section','nxw-card');c.id='nxw-facts';c.innerHTML='<h3>Что NOX вспомнил</h3><div id="nxw-fl"></div><p><button class="nxw-b" id="nxw-add">+ факт</button> <button class="nxw-b" id="nxw-pull">Подтянуть из его мыслей</button></p>';
 host.prepend(c);var fl=$('#nxw-fl',c);
 function save(){L.setItem('nox.facts.v1',JSON.stringify(facts_));L.setItem('nox.facts.text',facts_.join('\n'))}
 var facts_=facts();
 function draw(){fl.innerHTML='';if(!facts_.length)fl.append(el('div','', '<i>Пока пусто — NOX добавит факты, или добавь сам.</i>'));
  facts_.forEach(function(t,i){var r=el('div','nxw-fact');var d=el('div');d.contentEditable='true';d.textContent=t;d.onblur=function(){facts_[i]=d.textContent.trim();if(!facts_[i])facts_.splice(i,1);save();draw()};
   var x=el('button','nxw-b','✕');x.onclick=function(){facts_.splice(i,1);save();draw()};r.append(d,x);fl.append(r)})}
 draw();
 $('#nxw-add',c).onclick=function(){facts_.push('новый факт');save();draw();var l=fl.querySelectorAll('[contenteditable]');l[l.length-1].focus()};
 $('#nxw-pull',c).onclick=function(){fetch('/api/life',{cache:'no-store'}).then(function(r){return r.json()}).then(function(j){var t=j.thought||j.last_thought;if(t&&facts_.indexOf(t)<0){facts_.push(t);save();draw()}}).catch(function(){})}}
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
function init(){applyPlanet();planetPicker();bnav();memPanel();mic();lazy();depthUI();
 new MutationObserver(function(){depthUI()}).observe(D.body,{childList:true,subtree:true,attributes:true,attributeFilter:['aria-pressed']})}
if(D.readyState==='loading')D.addEventListener('DOMContentLoaded',init);else init();
})();
