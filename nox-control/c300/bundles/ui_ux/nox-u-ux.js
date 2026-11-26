/* U-UX v4 (готовые Shoelace: sl-skeleton, sl-card, sl-button variant=primary): короткий placeholder на главной; пустые состояния (.ds-empty с подсказкой и кнопкой «Спросить NOX»); скелетон вместо «Загрузка…» (.u-skel). Идемпотентно, без внешних запросов. */
(function(){ if(window.NOXuux&&window.NOXuux.v===4)return; var U=window.NOXuux={v:4};
 var EMPTY=/^(пусто|нет данных|ничего нет|нет записей|список пуст|данных нет|не найдено|нет событий|событий нет|нет элементов|empty|no data|no results)[.!…\s]*$/i;
 var LOAD=/^(загрузка|загружаю|loading)[.…\s]*$/i;
 function ask(){var f=document.querySelector('.nmc-fab,#nxmPill');if(f)f.click()}
 function empties(root){
  (root||document).querySelectorAll('.empty,.nodata,.no-data,[class*=empty],[class*=placeholder],p,div,span,li,td').forEach(function(e){
   if(e.dataset.uDone||e.children.length>1||e.closest('#nxdock,header,nav,.tb,sl-select,select,input,textarea,[contenteditable]'))return;
   var t=(e.textContent||'').trim(); if(t.length>40||!t)return;
   if(LOAD.test(t)){e.dataset.uDone='1';e.setAttribute('aria-busy','true');e.setAttribute('aria-label','Загрузка');e.innerHTML='<sl-skeleton effect="sheen" style="--border-radius:8px;width:140px;height:18px;display:inline-block"></sl-skeleton>';return}
   if(EMPTY.test(t)&&e.offsetHeight<400){e.dataset.uDone='1';
    if(e.tagName==='TD'||e.tagName==='LI'||e.tagName==='SPAN')return;
    e.classList.add('ds-empty');e.innerHTML='<sl-card class="u-card"><div class="ds-empty-in"><b></b><span>Пока пусто: данные появятся после первого действия или синхронизации.</span><sl-button variant="primary" size="large" class="ds-empty-cta">Спросить NOX</sl-button></div></sl-card>';
    e.querySelector('b').textContent='Здесь пока ничего нет';e.querySelector('.ds-empty-cta').addEventListener('click',ask)}
  })}
  var CTA={voice:['#k3-orb-b'],downloads:['#s4fr'],pdf:['#pdfSave'],index:['#app button,#app sl-button,#app a',/^Спросить NOX$/],system:['#s6Ask'],memory:['#s4mgo'],map:['#mpMe'],knowledge:['#refresh'],widgets:['#s6Ask'],projects:['#s6Ask'],music:['sl-button,button',/Добавить файлы/],news:['#app sl-button,#app button',/^Сводка NOX/],cinema:['.s2x',/^Смотреть/],mail:['#s4a0'],calendar:['.s4sl',/Новое событие/],settings:['#s6Ask'],creative:['#k8-chat .k4-btn.pri']};
 function setCta(e){e.classList.add('u-cta');if(e.tagName==='SL-BUTTON'){e.setAttribute('variant','primary');e.setAttribute('size','large')}}
 var FB=['#app sl-button[variant=primary]','#app button.pri','#app .k4-btn.pri','#app .btn.primary','#app button.primary','#s6Ask'];
 function cta(){var k=(location.pathname.split('/').pop()||'').replace(/\.html.*$/,'');var c=CTA[k];if(document.querySelector('.u-cta')||k==='chat')return;
  if(!c){for(var j=0;j<FB.length;j++){var f=document.querySelector(FB[j]);if(f&&f.offsetWidth&&!f.closest('#nxdock,header,.tb')){setCta(f);return}}return}
  var list=document.querySelectorAll(c[0]);for(var i=0;i<list.length;i++){var e=list[i];if(c[1]&&!c[1].test((e.textContent||'').trim()))continue;if(!e.offsetWidth)continue;setCta(e);var a=document.getElementById('s6Ask');if(a&&a!==e&&a.tagName==='SL-BUTTON'){a.classList.add('u-sec');a.setAttribute('variant','default')}break}}
 function clean(){
  document.querySelectorAll('[aria-busy=true][data-u-done]').forEach(function(e){if(!e.querySelector('sl-skeleton')){e.removeAttribute('aria-busy');e.removeAttribute('aria-label')}});
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
