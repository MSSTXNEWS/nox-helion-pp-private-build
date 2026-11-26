/* U-UX v1: короткий placeholder быстрого запроса на главной; имена для безымянных целей. Идемпотентно. */
(function(){ if(window.NOXuux)return; window.NOXuux=1;
 function run(){
  if(document.body&&document.body.dataset.page==='home'){
   document.querySelectorAll('input[placeholder*="Быстрый запрос"]').forEach(function(i){i.placeholder='Спросить NOX или найти'});
  }
 }
 run(); setTimeout(run,1500); setTimeout(run,4000);
})();
