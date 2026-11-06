/* Small menu of real route links; preserves existing approved page composition. */
(()=>{'use strict';
const header=document.querySelector('.topbar,.work-header');if(!header||document.querySelector('[data-nox-menu]'))return;
const nav=document.createElement('details');nav.dataset.noxMenu='1';nav.className='nox-route-menu';
const summary=document.createElement('summary');summary.textContent='Разделы';nav.append(summary);
const list=document.createElement('div');list.className='nox-route-list';
for(const [href,label] of [['./index.html','HOME'],['./chat.html','CHAT'],['./training.html','ОБУЧЕНИЕ'],['./models.html','МОДЕЛИ'],['./memory.html','ПАМЯТЬ'],['./system.html','СИСТЕМА'],['./install.html','УСТАНОВКА'],['./projects.html','ПРОЕКТЫ'],['./settings.html','НАСТРОЙКИ']]){
 const a=document.createElement('a');a.href=href;a.textContent=label;list.append(a)
}
nav.append(list);header.append(nav);
window.addEventListener('keydown',e=>{if(e.key==='Escape')nav.open=false});
})();