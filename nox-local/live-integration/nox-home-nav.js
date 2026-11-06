/* Original HOME buttons now navigate to real route pages, not inert modal tiles. */
(()=>{'use strict';
for(const [selector,path] of [['#modelBtn','./models.html'],['#memoryBtn','./memory.html']]){
 const el=document.querySelector(selector);if(!el)continue;
 el.addEventListener('click',e=>{e.preventDefault();e.stopImmediatePropagation();location.assign(path)},true);
}
})();