/* V22 owner controls: real source-locked worlds and portraits, no fake backend. */
(()=>{'use strict';
 const init=()=>{
  const body=document.body;
  if(body.dataset.page!=='index'||!body.classList.contains('nox-owner-cinema')||window.NOX_OWNER_RELEASE_V22)return;
  const mode=document.querySelector('button.nox-owner-mode');
  const coreLinks=[...document.querySelectorAll('.nox-owner-core')];
  const personas=[...document.querySelectorAll('.nox-owner-persona')];
  const originalControls=document.querySelector('section.home-palette-bottom.nox-orbital-controls');
  if(!mode||coreLinks.length!==8||personas.length!==5||!originalControls){
   console.warn('NOX_V22_OWNER_SOURCE_MISSING');return;
  }
  const legacyIDs=['CONSCIOUSNESS','PERSONA','ATLAS','VOICE','REFLECTION','CORE','NEXUS','FORGE'];
  const labels=['СОЗНАНИЕ','ЛИЧНОСТЬ','АТЛАС','ГОЛОС','РЕФЛЕКСИЯ','ЯДРО','СВЯЗИ','КУЗНИЦА'];
  coreLinks.forEach((link,i)=>{
   link.dataset.noxCoreId=legacyIDs[i];link.dataset.noxDisplayName=labels[i];
   link.setAttribute('aria-label',labels[i]+' · '+legacyIDs[i]+' · открыть существующий раздел');
   const span=link.querySelector('span');if(span)span.textContent=labels[i];
  });
  // Open the *real* approved local portrait. No pretence of video or Persona memory.
  const names=['КАЙРЕН ВОСС','АДРИАН МЕРРОУ','ЛЕОН АРДИС','ЭЛИНА ВЕЙЛ','КАССИЕН ВЕЙР'];
  const ids=['kv','am','la','ev','kw'];
  const dialog=document.createElement('dialog');dialog.className='nox-v22-persona-dialog';
  const heading=document.createElement('h2');
  const photo=document.createElement('img');
  const caption=document.createElement('p');
  caption.textContent='Утверждённый портрет. Видео и отдельный контекст Persona требуют подключения и проверки существующего NOX.';
  const close=document.createElement('button');close.type='button';close.textContent='ЗАКРЫТЬ';
  close.addEventListener('click',()=>dialog.close());
  dialog.addEventListener('click',e=>{if(e.target===dialog)dialog.close()});
  dialog.append(heading,photo,caption,close);document.body.append(dialog);
  personas.forEach((button,i)=>{
   const label=button.querySelector('span');if(label)label.textContent=names[i];
   button.setAttribute('aria-label','Посмотреть утверждённый портрет: '+names[i]);
   button.addEventListener('click',e=>{
    e.preventDefault();e.stopImmediatePropagation();
    heading.textContent=names[i];
    photo.src='./assets/nox-owner-approved/nox-owner-persona-'+ids[i]+'.webp';
    photo.alt='Утверждённый портрет '+names[i];
    if(typeof dialog.showModal==='function')dialog.showModal();
   },true);
  });
  const panelCount=()=>originalControls.querySelectorAll('button').length;
  const syncMode=()=>{
   const isPBR=body.dataset.noxOwnerLayout==='PBR';
   mode.textContent=isPBR?'✦ 8 ЯДЕР':'◆ 14 МИРОВ';
   mode.setAttribute('aria-label',isPBR?'Вернуться к восьми CoreID':'Показать исходные 14 объёмных планет и астероидов');
   mode.setAttribute('aria-pressed',String(isPBR));
   mode.title='6 цветовых планет · 5 миров · 3 режима MAX/BALANCED/ECO';
  };
  const controlsToggle=[...document.querySelectorAll('.nox-owner-actions button')].find(b=>/НАСТРОЙКИ СЦЕНЫ|ЗАКРЫТЬ НАСТРОЙКИ/.test(b.textContent));
  if(controlsToggle){originalControls.id='nox-owner-world-control-panel';controlsToggle.setAttribute('aria-controls',originalControls.id);}
  originalControls.setAttribute('aria-label','Четырнадцать оригинальных графических переключателей NOX');
  mode.addEventListener('click',()=>{
   const open=body.dataset.noxOwnerLayout==='PBR';
   body.dataset.noxOwnerControls=String(open);
   if(controlsToggle){controlsToggle.setAttribute('aria-expanded',String(open));controlsToggle.textContent=open?'✕ ЗАКРЫТЬ НАСТРОЙКИ':'✧ НАСТРОЙКИ СЦЕНЫ';}
   syncMode();
  });
  if(panelCount()!==14)console.warn('NOX_V22_14_WORLD_SELECTOR_HOLD',panelCount());
  syncMode();
  // The historical Orbit V14 loader adds five CSS sheets asynchronously.
  // Ensure this reversible repair remains last, instead of rewriting the donor files.
  const fidelityStyle=document.querySelector('link[href*="nox-owner-release-v22.css"]');
  if(fidelityStyle){
   const keepLast=()=>{if(fidelityStyle.parentElement===document.head&&document.head.lastElementChild!==fidelityStyle)document.head.append(fidelityStyle);};
   const observer=new MutationObserver(records=>{
    if(records.some(r=>[...r.addedNodes].some(n=>n.nodeType===1&&n!==fidelityStyle&&
      (n.tagName==='STYLE'||(n.tagName==='LINK'&&n.rel==='stylesheet')))))keepLast();
   });
   observer.observe(document.head,{childList:true});
   keepLast();
   setTimeout(()=>observer.disconnect(),7000);
  }
  window.NOX_OWNER_RELEASE_V22=Object.freeze({
   version:'V22',engine:'ORIGINAL_D02_AND_PHYSICAL_WORLDS_V7',
   coreCount:coreLinks.length,worldCount:panelCount,approvedPortraits:personas.length,
   layout:()=>body.dataset.noxOwnerLayout,physicalGpuAcceptance:'HOLD',backendAcceptance:'HOLD'
  });
 };
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
