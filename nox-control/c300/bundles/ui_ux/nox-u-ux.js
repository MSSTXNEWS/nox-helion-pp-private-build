/* U-UX v2: короткий placeholder на главной; пустые состояния (.ds-empty с подсказкой и кнопкой «Спросить NOX»); скелетон вместо «Загрузка…» (.u-skel). Идемпотентно, без внешних запросов. */
(function(){ if(window.NOXuux&&window.NOXuux.v===2)return; var U=window.NOXuux={v:2};
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
 function run(){
  if(document.body&&document.body.dataset.page==='home')document.querySelectorAll('input[placeholder*="Быстрый запрос"]').forEach(function(i){i.placeholder='Спросить NOX или найти'});
  try{empties()}catch(x){}
 }
 var tm; function later(){clearTimeout(tm);tm=setTimeout(run,600)}
 function start(){run();[1500,4000,9000].forEach(function(d){setTimeout(run,d)});
  if(window.MutationObserver){new MutationObserver(later).observe(document.body,{childList:true,subtree:true});}}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
})();
