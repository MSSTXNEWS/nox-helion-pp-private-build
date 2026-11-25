/* L: клиентская логика живости (без вёрстки). Подключение: <script src="nox-l-core.js"></script> в chat.html (делает S1). Событие 'nox-l' отдаёт данные UI. */
(function(){
  var Q={quiet:[23,7],maxPro:3};
  function emit(t,d){document.dispatchEvent(new CustomEvent('nox-l',{detail:{type:t,data:d}}));}
  function inQuiet(h){var a=Q.quiet[0],b=Q.quiet[1];return a>b?(h>=a||h<b):(h>=a&&h<b);}
  window.noxL={
    greeting:function(lastTs){var h=new Date().getHours(),gap=lastTs?(Date.now()-lastTs)/36e5:null;
      var p=h<5?'Не спится? Я рядом, но лучше отдохнуть.':h<12?'Доброе утро.':h<18?'Добрый день.':'Добрый вечер.';
      if(gap!==null&&gap>48)p+=' Давно не заглядывали, с возвращением.';return p;},
    quietNow:function(){return inQuiet(new Date().getHours());},
    canProactive:function(sentToday){return !this.quietNow()&&sentToday<Q.maxPro;},
    busy:function(){return fetch('/api/chat/health').then(function(r){return r.json();}).then(function(j){var b=!(j.core&&j.core.up);if(b)emit('busy','Модель сейчас занята обучением, ответ может занять до 2 минут.');return b;}).catch(function(){return false;});},
    status:function(){return fetch('/api/nox/status').then(function(r){return r.json();}).then(function(j){emit('status',j);return j;}).catch(function(){return null;});}
  };
})();
