/* NOX V18 shared behavior: existing controls stay functional, no visible dropdowns. */
(()=>{'use strict';
 if(window.NOX_WOW_GLOBAL_V18)return;
 const managed=new WeakMap();
 function convert(select){
  if(!select||managed.has(select))return;
  const options=[...select.options].filter(o=>!o.hidden);
  if(!options.length){select.dataset.noxWowConverted='true';select.tabIndex=-1;return;}
  const group=document.createElement('div');
  group.className='nox-wow-choice-group';
  group.setAttribute('role','group');
  const label=select.labels?.[0]?.textContent?.trim()||select.getAttribute('aria-label')||select.name||'Выбор';
  group.setAttribute('aria-label',label);
  const update=()=>{
   const current=[...group.querySelectorAll('button')];
   current.forEach(btn=>{const opt=options.find(o=>o.value===btn.dataset.value);const chosen=!!opt&&(select.multiple?opt.selected:btn.dataset.value===select.value);btn.setAttribute('aria-pressed',String(chosen));btn.disabled=select.disabled||btn.dataset.optionDisabled==='true'});
  };
  for(const opt of options){
   const btn=document.createElement('button');btn.type='button';btn.className='nox-wow-choice';
   btn.dataset.value=opt.value;btn.dataset.optionDisabled=String(opt.disabled);
   btn.textContent=opt.textContent.trim();
   btn.disabled=select.disabled||opt.disabled;
   btn.addEventListener('click',()=>{
    if(select.disabled||opt.disabled)return;
    if(select.multiple){opt.selected=!opt.selected}else{select.value=opt.value}
    select.dispatchEvent(new Event('input',{bubbles:true}));
    select.dispatchEvent(new Event('change',{bubbles:true}));
    update();
   });
   group.appendChild(btn);
  }
  select.after(group);
  select.dataset.noxWowConverted='true';
  select.tabIndex=-1;
  select.addEventListener('change',update);
  managed.set(select,{group,update});
  update();
 }
 function glass(root=document){
  const selector='.helion-monitor,.helion-system,.helion-journal,.sidebar,.panel,.card,.nox-glass-surface';
  const nodes=[...(root.matches?.(selector)?[root]:[]),...(root.querySelectorAll?.(selector)||[])];
  for(const host of nodes){
   if(host.classList.contains('nox-wow-glass-host')||host.closest('.nox-wow-choice-group'))continue;
   host.classList.add('nox-wow-glass-host','lg-host');
   for(const name of ['lg-layer','lg-sheen']){const el=document.createElement('span');el.className=name;el.setAttribute('aria-hidden','true');host.prepend(el)}
  }
 }
 function scan(root=document){
  if(root.nodeType!==1&&root.nodeType!==9)return;
  if(root.matches?.('select'))convert(root);
  root.querySelectorAll?.('select:not([data-nox-wow-converted])').forEach(convert);
 }
 function boot(){
  scan();glass();
  const observer=new MutationObserver(records=>{
   for(const record of records){
    if(record.type==='childList'){
     for(const node of record.addedNodes){scan(node);if(node.nodeType===1 && !node.classList?.contains('lg-layer') && !node.classList?.contains('lg-sheen'))glass(node)}
     if(record.target.tagName==='SELECT'){
      const data=managed.get(record.target);
      if(data){data.group.remove();managed.delete(record.target);record.target.removeAttribute('data-nox-wow-converted');convert(record.target)}
     }
    }
    if(record.type==='attributes'&&record.target.tagName==='SELECT')managed.get(record.target)?.update();
   }
  });
  observer.observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['disabled','value']});
  window.NOX_WOW_GLOBAL_V18=Object.freeze({
   convertedSelects:()=>document.querySelectorAll('select[data-nox-wow-converted]').length,
   buttonGroups:()=>document.querySelectorAll('.nox-wow-choice-group').length,
   page:()=>document.body.dataset.page||location.pathname,
   source:'INTEGRATED_SHARED_UI'
  });
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
