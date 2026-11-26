/* U-UX v3 (+главный CTA по странице): короткий placeholder на главной; пустые состояния (.ds-empty с подсказкой и кнопкой «Спросить NOX»); скелетон вместо «Загрузка…» (.u-skel). Идемпотентно, без внешних запросов. */
(function(){ if(window.NOXuux&&window.NOXuux.v===3)return; var U=window.NOXuux={v:3};
 var EMPTY=/^(пусто|нет данных|ничего нет|нет записей|список пуст|данных нет|не найдено|нет событий|событий нет|нет элементов|empty|no data|no results)[.!…\s]*$/i;
 var LOAD=/^(загрузка|загружаю|loading)[.…\s]*$/i;
 function ask(){var f=document.querySelector('.nmc-fab,#nxmPill');if(f)f.click()}
 function empties(root){
  (root||document).querySelectorAll('.empty,.nodata,.no-data,[class*=empty],[class*=placeholder],p,div,span,li,td').forEach(function(e){
   if(e.dataset.uDone||e.children.length>1||e.closest('#nxdock,header,nav,.tb,sl-select,select,input,textarea,[contenteditable]'))return;
   var t=(e.textContent||'').trim(); if(t.length>40||!t)return;
   if(LOAD.test(t)){e.dataset.uDone='1';e.setAttribute('aria-busy','true');e.textContent='';e.classList.add('u-skel');e.style.minHeight='18px';e.style.minWidth='120px';e.setAttribute('aria-label','Загрузка');return}
   if(EMPTY.test(t)&&e.offsetHeight<400){e.dataset.uDone='1';
    if(e.tagName==='TD'||e.tagName==='LI'||e.tagName==='SPAN')return;
    e.classList.add('ds-empty');e.innerHTML='<b></b><span>Пока пусто: данные появятся после первого действия или синхронизации.</span>';
    e.querySelector('b').textContent='Здесь пока ничего нет';
    var b=document.createElement('button');b.type='button';b.className='ds-empty-cta';b.textContent='Спросить NOX';b.onclick=ask;e.appendChild(b)}
  })}
  var CTA={voice:['#k3-orb-b'],downloads:['#s4fr'],pdf:['#pdfSave'],index:['#app button,#app sl-button,#app a',/^Спросить NOX$/],system:['#s6Ask'],memory:['#s4mgo'],map:['#mpMe'],knowledge:['#refresh'],widgets:['#s6Ask'],projects:['#s6Ask'],music:['sl-button,button',/Добавить файлы/],news:['#app sl-button,#app button',/^Сводка NOX/],cinema:['.s2x',/^Смотреть/],mail:['#s4a0'],calendar:['.s4sl',/Новое событие/],settings:['#s6Ask'],creative:['#k8-chat .k4-btn.pri']};
 var FB=['#app sl-button[variant=primary]','#app button.pri','#app .k4-btn.pri','#app .btn.primary','#app button.primary','#s6Ask'];
 function cta(){var k=(location.pathname.split('/').pop()||'').replace(/\.html.*$/,'');var c=CTA[k];if(document.querySelector('.u-cta')||k==='chat')return;
  if(!c){for(var j=0;j<FB.length;j++){var f=document.querySelector(FB[j]);if(f&&f.offsetWidth&&!f.closest('#nxdock,header,.tb')){f.classList.add('u-cta');return}}return}
  var list=document.querySelectorAll(c[0]);for(var i=0;i<list.length;i++){var e=list[i];if(c[1]&&!c[1].test((e.textContent||'').trim()))continue;if(!e.offsetWidth)continue;e.classList.add('u-cta');var a=document.getElementById('s6Ask');if(a&&a!==e)a.classList.add('u-sec');break}}
 function clean(){
  document.querySelectorAll('.u-skel[data-u-done]').forEach(function(e){if((e.textContent||'').trim()){e.classList.remove('u-skel');e.removeAttribute('aria-busy');e.removeAttribute('aria-label');e.style.minHeight='';e.style.minWidth=''}});
  document.querySelectorAll('.ds-empty[data-u-done]').forEach(function(e){if(!e.querySelector('.ds-empty-cta')){e.classList.remove('ds-empty')}});
 }
 function run(){
  if(document.body&&document.body.dataset.page==='home')document.querySelectorAll('input[placeholder*="Быстрый запрос"]').forEach(function(i){i.placeholder='Спросить NOX или найти'});
  try{clean()}catch(x){}
  try{empties()}catch(x){}
  try{cta()}catch(x){}
 }
 var tm; function later(){clearTimeout(tm);tm=setTimeout(run,600)}
 function start(){run();[1500,4000,9000].forEach(function(d){setTimeout(run,d)});
  if(window.MutationObserver){new MutationObserver(later).observe(document.body,{childList:true,subtree:true});}}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
})();
