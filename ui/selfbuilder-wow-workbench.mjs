/** Owner-reviewed NOX WOW design workbench for existing secondary MENU V2.
 * Source-only UI donor: must be wired to the ORIGINAL OneHost/P02/S03 bridge.
 * Never mounts in D02 HOME, creates a ninth MENU tile, or calls native code
 * directly. No innerHTML, fake LIVE telemetry, code execution or hidden consent.
 */
export const NOX_MENU_SECTIONS=Object.freeze([
 'РАБОТА','ИНТЕЛЛЕКТ','ЗНАНИЯ','ТВОРЧЕСТВО','ЛЮДИ','РАЗВИТИЕ','МИР','СИСТЕМА'
]);
export const NOX_LAYOUTS=Object.freeze(['ORBITAL','CINEMATIC','WORKSPACE']);
const sections=new Set(NOX_MENU_SECTIONS),layouts=new Set(NOX_LAYOUTS);
const reg=/^[a-z][a-z0-9-]{1,79}$/;
function safe(text,max=180){return typeof text==='string'&&text.length>0&&text.length<=max&&![...text].some(c=>c<' ');}

/** Data-only projection. Model claims NEVER become a native handler. */
export function previewDesign(proposal,id){
 if(!proposal||proposal.schema!=='NOX-WOW-DESIGN-REVIEW-v1'||proposal.state!=='OWNER_REVIEW_REQUIRED'||
   !/^[a-f0-9]{64}$/.test(proposal.proposal_sha256||'')||!Array.isArray(proposal.variants)||proposal.variants.length!==3)
   throw Error('TRUSTED_WOW_REVIEW_RECEIPT_REQUIRED');
 const selected=proposal.variants.find(v=>v.id===id);
 if(!selected||!layouts.has(selected.layout)||!safe(selected.title,130)||!Array.isArray(selected.screens)||selected.screens.length<1||selected.screens.length>5)
   throw Error('DESIGN_VARIANT_NOT_ADMITTED');
 const screens=selected.screens.map(screen=>{
   if(!sections.has(screen.section)||!safe(screen.title,120)||!reg.test(screen.route_id)||
     !Array.isArray(screen.buttons)||screen.buttons.length<1||screen.buttons.length>10)
     throw Error('MENU_V2_OR_BUTTON_CONTRACT_HOLD');
   const buttons=screen.buttons.map(b=>{
     if(!safe(b.label,90)||!reg.test(b.action_id)||b.status!=='CONTRACT_REQUIRED')
       throw Error('UNVERIFIED_NATIVE_HANDLER_DENIED');
     return {label:b.label,action_id:b.action_id,state:'CONTRACT_REQUIRED'};
   });
   return {section:screen.section,title:screen.title,route_id:screen.route_id,buttons};
 });
 return {id,layout:selected.layout,title:selected.title,screens,sha256:proposal.proposal_sha256,
   status:'OWNER_REVIEW_REQUIRED',notLive:true};
}
/** Never infer an enabled background worker from UI state or local storage. */
export function backgroundToggleState(receipt){
 if(!receipt||receipt.schema!=='NOX-SELFBUILDER-BACKGROUND-v1'||
    receipt.source!=='ORIGINAL_S03'||typeof receipt.enabled!=='boolean'||
    !Number.isSafeInteger(receipt.revision)||receipt.revision<0||
    !['OFF','ON','RUNNING','STOPPING'].includes(receipt.status)||
    receipt.auto_code!==false||receipt.auto_merge!==false||receipt.auto_install!==false)
  return {ready:false,enabled:false,label:'Фоновое саморазвитие · HOLD',
    note:'Нет подтверждённого состояния в памяти S03',switchLabel:'Недоступно'};
 return {ready:true,enabled:receipt.enabled,
   label:'Фоновое саморазвитие · '+(receipt.status==='RUNNING'?'РАБОТАЕТ':
     receipt.status==='STOPPING'?'ОСТАНАВЛИВАЕТСЯ':receipt.enabled?'ВКЛ':'ВЫКЛ'),
   note:'Только идеи на согласование · не чаще раза в 24 часа · без изменения EXE',
   switchLabel:receipt.enabled?'Выключить':'Включить'};
}

function el(doc,tag,cls,content=''){
 const node=doc.createElement(tag);if(cls)node.className=cls;node.textContent=content;return node;
}
export function mountWowDesignWorkbench({root,documentRef,getProposal,ownerApprove,
  getBackgroundState=null,setBackgroundEnabled=null,onError=()=>{}}){
 if(!root||typeof getProposal!=='function'||typeof ownerApprove!=='function')throw Error('ORIGINAL_NATIVE_OWNER_REQUIRED');
 const doc=documentRef||root.ownerDocument;
 if(!doc||root.dataset?.noxPage==='home'||root.closest?.('[data-nox-page="home"]'))throw Error('D02_HOME_LOCK');
 if(root.querySelector?.('[data-nox-wow-studio="owner-v1"]'))throw Error('ONE_WORKBENCH_ONLY');
 const wrap=el(doc,'section','nox-wow-workbench');wrap.dataset.noxWowStudio='owner-v1';
 wrap.append(el(doc,'h3','nox-wow-workbench__head','Эскизы NOX · три варианта'));
 wrap.append(el(doc,'p','nox-wow-workbench__lead','Сначала согласование идеи. Новые кнопки не будут работать, пока нет проверенных обработчиков.'));
 const background=el(doc,'section','nox-wow-workbench__background');
 background.dataset.noxBackgroundControl='true';
 const bgCopy=el(doc,'div','nox-wow-workbench__background-copy');
 const bgTitle=el(doc,'strong','nox-wow-workbench__background-title','Фоновое саморазвитие · HOLD');
 const bgNote=el(doc,'p','nox-wow-workbench__background-note',
   'Без подтверждённого S03 режима предложения в фоне не запускаются');
 const bgSwitch=el(doc,'button','nox-wow-workbench__background-switch','Недоступно');
 bgSwitch.type='button';bgSwitch.disabled=true;bgSwitch.setAttribute('aria-pressed','false');
 bgCopy.append(bgTitle,bgNote);background.append(bgCopy,bgSwitch);wrap.append(background);

 const options=el(doc,'div','nox-wow-workbench__variants');
 const stage=el(doc,'div','nox-wow-workbench__stage');
 const message=el(doc,'p','nox-wow-workbench__status','HOLD · ожидаем проверенное предложение из S03');
 message.setAttribute('role','status');message.setAttribute('aria-live','polite');
 const approve=el(doc,'button','nox-wow-workbench__approve','Согласовать для создания кода');approve.type='button';approve.disabled=true;
 const refresh=el(doc,'button','nox-wow-workbench__refresh','Обновить предложения');refresh.type='button';
 wrap.append(options,stage,approve,refresh,message);root.append(wrap);
 let current=null,selection=null,working=false,disposed=false;
 let backgroundReceipt=null,backgroundBusy=false;
 const hasBackground=typeof getBackgroundState==='function'&&typeof setBackgroundEnabled==='function';
 function drawBackground(){
   const view=backgroundToggleState(backgroundReceipt);
   bgTitle.textContent=view.label;bgNote.textContent=view.note;
   bgSwitch.textContent=backgroundBusy?'Сохраняем в S03…':view.switchLabel;
   bgSwitch.disabled=disposed||backgroundBusy||!hasBackground||!view.ready;
   bgSwitch.setAttribute('aria-pressed',view.ready&&view.enabled?'true':'false');
   background.dataset.state=!view.ready?'HOLD':view.enabled?'ON':'OFF';
 }
 async function refreshBackground(){
   if(disposed||!hasBackground)return;
   try{
     const receipt=await getBackgroundState();if(disposed)return;
     backgroundReceipt=receipt;drawBackground();
   }catch(error){if(!disposed){backgroundReceipt=null;drawBackground();onError(error);}}
 }
 bgSwitch.addEventListener('click',async()=>{
   const old=backgroundToggleState(backgroundReceipt);
   if(disposed||backgroundBusy||!old.ready||!hasBackground)return;
   backgroundBusy=true;drawBackground();
   try{
     const requested=!old.enabled;
     const ack=await setBackgroundEnabled(requested);
     if(disposed)return;
     // Native result is still only a hint; query persisted S03 state afterwards.
     if(!backgroundToggleState(ack).ready||ack.enabled!==requested)
       throw Error('S03_BACKGROUND_SWITCH_NOT_CONFIRMED');
     const readback=await getBackgroundState();
     if(disposed)return;
     if(!backgroundToggleState(readback).ready||readback.enabled!==requested)
       throw Error('S03_BACKGROUND_READBACK_MISMATCH');
     backgroundReceipt=readback;
   }catch(error){if(!disposed){backgroundReceipt=null;onError(error);}}
   finally{backgroundBusy=false;if(!disposed)drawBackground();}
 });
 drawBackground();
 void refreshBackground();

 function render(){
   options.replaceChildren();stage.replaceChildren();approve.disabled=true;
   const data=current;
   if(!data){message.textContent='HOLD · утверждённого source-verified предложения нет';return;}
   if(!selection||!data.variants.some(v=>v.id===selection))selection=data.variants[0]?.id||null;
   for(const variant of data.variants||[]){
     let model;
     try{model=previewDesign(data,variant.id);}catch(ex){onError(ex);message.textContent='HOLD · '+ex.message;return;}
     const button=el(doc,'button','nox-wow-workbench__variant',model.title);
     button.type='button';button.dataset.variantId=model.id;
     button.dataset.active=model.id===selection?'true':'false';
     button.addEventListener('click',()=>{if(working||disposed)return;selection=model.id;render();});
     options.append(button);
   }
   if(!selection)return;
   const model=previewDesign(data,selection);
   stage.dataset.layout=model.layout;stage.append(el(doc,'h4','nox-wow-workbench__title',model.title));
   stage.append(el(doc,'p','nox-wow-workbench__warning','ПРЕДПРОСМОТР · НЕ УСТАНОВЛЕНО'));
   for(const screen of model.screens){
     const panel=el(doc,'div','nox-wow-workbench__screen');
     panel.append(el(doc,'p','nox-wow-workbench__section',screen.section));
     panel.append(el(doc,'h5','nox-wow-workbench__title',screen.title));
     const actions=el(doc,'div','nox-wow-workbench__actions');
     for(const b of screen.buttons){
       const btn=el(doc,'button','nox-wow-workbench__button',b.label+' · CONTRACT_REQUIRED');
       btn.type='button';btn.disabled=true;btn.title='Ожидает проверки обработчика в оригинальном NOX';actions.append(btn);
     }
     panel.append(actions);stage.append(panel);
   }
   approve.disabled=working;message.textContent='На согласовании · '+model.id+' · '+model.layout;
 }
 async function reload(){
   if(disposed||working)return;
   try{const p=await getProposal();if(disposed)return;current=p;selection=p?.variants?.[0]?.id||null;render();}
   catch(ex){current=null;render();onError(ex);message.textContent='HOLD · нет подтверждённой связи с S03';}
 }
 approve.addEventListener('click',async()=>{
   if(disposed||working||!current||!selection)return;
   working=true;approve.disabled=true;message.textContent='REQUESTED · ожидаем отдельное подтверждение владельца';
   try{
     const result=await ownerApprove({action:'selfbuilder.design.approve',variant_id:selection,
           proposal_sha256:current.proposal_sha256,source_head:current.source_head});
     if(disposed)return;
     message.textContent=result?.state==='OWNER_ACCEPTED_DESIGN'
       ?'СОГЛАСОВАНО · только идея; код и установка требуют отдельных проверок'
       :'HOLD · согласование не подтверждено';
   }catch(ex){if(!disposed){onError(ex);message.textContent='HOLD · согласование не подтверждено';}}
   finally{working=false;if(!disposed)approve.disabled=false;}
 });
 refresh.addEventListener('click',reload);
 return Object.freeze({refresh:async()=>{await Promise.all([reload(),refreshBackground()]);},
    refreshBackground,destroy(){disposed=true;wrap.remove();}});
}