/** NOX MENU V2 extension, mounted ONLY by the existing trusted WPF/WebView2 host.
 *  NO changes to HOME, original D02 assets, eight MENU tiles or eight CoreID.
 *  Receives verified native state and sends requests through the EXISTING host;
 *  no direct privileged bridge, simulated GPU training or autostart.
 */
import {LOGICAL_MENU_PARENTS} from '../proposals/P01/WOW-MAX10/scene-contract.mjs';
/*
 * Bundled exact SVG paths from Tabler Icons (MIT), official source:
 * https://github.com/tabler/tabler-icons/tree/main/icons/outline
 * Individual Git blobs: code 282fd111276a24b140314421b8d7e0629395c9b1;
 * arrow-left 182b91c5efc24129dd14bd29d31a842f2e5362d2;
 * player-stop f292282b73d38f2d175b3918a38906ea6bd3a91f.
 * MIT License. Copyright (c) 2020-2026 Paweł Kuna.
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 */
export const P01_TABLER_PATHS=Object.freeze({
 code:Object.freeze(['M7 8l-4 4l4 4','M17 8l4 4l-4 4','M14 4l-4 16']),
 back:Object.freeze(['M5 12l14 0','M5 12l6 6','M5 12l6 -6']),
 stop:Object.freeze(['M5 7a2 2 0 0 1 2 -2h10a2 2 0 0 1 2 2v10a2 2 0 0 1 -2 2h-10a2 2 0 0 1 -2 -2l0 -10'])
});
function p01Icon(doc,key){
 if(typeof doc?.createElementNS!=='function'||!Object.hasOwn(P01_TABLER_PATHS,key))return null;
 const ns='http://www.w3.org/2000/svg',svg=doc.createElementNS(ns,'svg');
 for(const [k,v] of Object.entries({viewBox:'0 0 24 24',width:'20',height:'20',
   fill:'none',stroke:'currentColor','stroke-width':'1.65',
   'stroke-linecap':'round','stroke-linejoin':'round','aria-hidden':'true',focusable:'false'}))
   svg.setAttribute(k,v);
 svg.setAttribute('class','nox-sb-icon');
 for(const d of P01_TABLER_PATHS[key]){
   const path=doc.createElementNS(ns,'path');path.setAttribute('d',d);svg.append(path);
 }
 return svg;
}
// Native Web Animations API already ships in WebView2. No second rendering engine.
function animateSelectedWorld(doc,button){
 const view=doc?.defaultView;
 if(view?.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches)return false;
 if(typeof button?.animate!=='function')return false;
 button.animate([
  {transform:'translateY(0) scale(1)',filter:'brightness(1)'},
  {transform:'translateY(-3px) scale(1.015)',filter:'brightness(1.16)'},
  {transform:'translateY(0) scale(1)',filter:'brightness(1)'}
 ],{duration:320,easing:'cubic-bezier(.22,1,.36,1)',iterations:1});
 return true;
}

// Use the approved original eight sections as physical navigation; ten logical
// worlds are child views of those EXISTING tiles, not new top-level graphics.
const P01_TILE_LABELS=Object.freeze({
 work:'РАБОТА',intelligence:'ИНТЕЛЛЕКТ',knowledge:'ЗНАНИЯ',
 creative:'ТВОРЧЕСТВО',people:'ЛЮДИ',development:'РАЗВИТИЕ',
 world:'МИР',system:'СИСТЕМА'
});
const P01_WORLD_LABELS=Object.freeze({
 work:'Проекты и задачи',intelligence:'Исследования и модели',
 knowledge:'Память и источники',learning:'Обучение и развитие',
 entertainment:'Кино и развлечения',people:'Люди и общение',
 creative:'Студия творчества',business:'Бизнес и проекты',
 world:'Мир и сценарии',pc:'Мой ПК и NOX'
});
export const P01_MENU_WORLD_NAV=Object.freeze(Object.entries(LOGICAL_MENU_PARENTS)
 .map(([id,parent])=>Object.freeze({id,label:P01_WORLD_LABELS[id],section:P01_TILE_LABELS[parent]})));
export function menuWorldsForSection(section){
 return P01_MENU_WORLD_NAV.filter(world=>world.section===section);
}
export const MENU_V2_SECTIONS = Object.freeze(['РАБОТА','ИНТЕЛЛЕКТ','ЗНАНИЯ','ТВОРЧЕСТВО','ЛЮДИ','РАЗВИТИЕ','МИР','СИСТЕМА']);
export const SELFBUILDER_MENU = Object.freeze([
  {section:'РАЗВИТИЕ', routeId:'evolution', label:'Саморазвитие',actionId:'selfbuilder.worker.status',mode:'read'},
  {section:'РАЗВИТИЕ', routeId:'study-queue',label:'План обучения',actionId:'selfbuilder.study.queue',mode:'read'},
  {section:'РАЗВИТИЕ', routeId:'learning-proofs',label:'Доказательства обучения',actionId:'selfbuilder.learning.proofs',mode:'read'},
  {section:'РАЗВИТИЕ', routeId:'weights',label:'Веса и адаптеры',actionId:'selfbuilder.seed.inspect',mode:'read'},
  {section:'РАЗВИТИЕ', routeId:'gpu-training',label:'Обучение на GPU',actionId:'selfbuilder.train.request',mode:'restricted'},
  {section:'РАЗВИТИЕ',routeId:'weights',label:'Объединить адаптер',actionId:'training.merge',mode:'restricted'},
  {section:'РАЗВИТИЕ',routeId:'weights',label:'Импортировать результат обучения',actionId:'training.import',mode:'restricted'},
  {section:'РАЗВИТИЕ',routeId:'weights',label:'Активировать проверенный адаптер',actionId:'training.activate',mode:'restricted'},
  {section:'РАЗВИТИЕ',routeId:'weights',label:'Откатить адаптер',actionId:'training.rollback',mode:'restricted'},
  {section:'СИСТЕМА',routeId:'model-library',label:'Модель программиста',actionId:'selfbuilder.coding.models',mode:'read'},
  {section:'СИСТЕМА',routeId:'core-status',label:'Статус ядер',actionId:'selfbuilder.worker.status',mode:'read'},
  {section:'РАБОТА',routeId:'commands',label:'Задания программиста',actionId:'selfbuilder.propose',mode:'restricted'},
  {section:'РАБОТА',routeId:'progress',label:'Проверенные улучшения',actionId:'selfbuilder.worker.status',mode:'read'},
  // Native-only source/code subsection under the existing eight MENU tiles.
  {section:'РАЗВИТИЕ',routeId:'evolution',label:'Библиотека исходников',actionId:'selfbuilder.sources.inspect',mode:'read',subview:'code'},
  {section:'РАЗВИТИЕ',routeId:'model-library',label:'Проверить модели программиста',actionId:'selfbuilder.coding.models',mode:'read',subview:'code'},
  {section:'РАЗВИТИЕ',routeId:'commands',label:'Создать кандидат кода',actionId:'selfbuilder.propose',mode:'restricted',subview:'code'},
  {section:'РАЗВИТИЕ',routeId:'progress',label:'Мои задания',actionId:'selfbuilder.worker.status',mode:'read',subview:'code'},
  {section:'РАЗВИТИЕ',routeId:'commands',label:'STOP самодописания',actionId:'selfbuilder.worker.stop',mode:'restricted',subview:'code'}
]);
const VALID=new Set(['VERIFIED','RUNNING','IDLE','PAUSED','HOLD','OFFLINE','NOT_INSTALLED','ERROR','PENDING','AVAILABLE','NATIVE_REQUEST_AVAILABLE']);
function status(value){return VALID.has(value)?value:'HOLD';}
function make(doc,tag,cls,text){const x=doc.createElement(tag);if(cls)x.className=cls;if(text)x.textContent=text;return x;}
export function mountSelfBuilderMenuV2({root,invokeNative,getTrustedState,ownerApprovedRoute,documentRef,getCurrentSection,getTrainingJobs=()=>[]}){
  if(!root || typeof invokeNative!=='function' || typeof getTrustedState!=='function'||
     typeof ownerApprovedRoute!=='function')throw Error('NOX_NATIVE_MENU_HOST_REQUIRED');
  const doc=documentRef||root.ownerDocument;
  if(!doc)throw Error('DOM_REQUIRED');
  if(root.dataset?.noxPage==='home'||root.closest?.('[data-nox-page="home"]'))throw Error('D02_HOME_LOCK');
  if(root.querySelector?.('[data-nox-selfbuilder="v2"]'))throw Error('DUPLICATE_MENU_EXTENSION');
  const wrapper=make(doc,'section','nox-sb-panel');wrapper.dataset.noxSelfbuilder='v2';
  wrapper.dataset.noxView='source-candidate';
  const heading=make(doc,'h2','nox-sb-heading','NOX · Эволюция и программирование');
  const info=make(doc,'p','nox-sb-subtitle','Настоящие задания, модели и обучение. Данные только из подтверждённого ядра.');
  // Reuse the existing ONE menu-detail panel, native client, and tile styles.
  // Sub-world selection is navigation only; it does not claim a backend action.
  const worldSection=make(doc,'section','nox-sb-sourcehub');
  worldSection.dataset.noxWorlds='canonical-10-within-8';
  const worldHeading=make(doc,'h3','nox-sb-sourcehub__title','Подразделы NOX');
  const worldGrid=make(doc,'div','nox-sb-grid');
  const worldFeedback=make(doc,'p','nox-sb-feedback','Выберите подраздел');
  worldFeedback.setAttribute('role','status');worldFeedback.setAttribute('aria-live','polite');
  const backWorld=make(doc,'button','nox-sb-tile','← Все подразделы');
  backWorld.type='button';backWorld.hidden=true;
  const backIcon=p01Icon(doc,'back');if(backIcon)backWorld.prepend(backIcon);
  worldSection.append(worldHeading,worldGrid,backWorld,worldFeedback);
  let activeWorld=null;
  const worldButtons=[];
  for(const world of P01_MENU_WORLD_NAV){
    const b=make(doc,'button','nox-sb-tile',world.label);
    b.type='button';b.dataset.noxWorld=world.id;b.dataset.noxWorldParent=world.section;
    b.addEventListener('click',()=>{
      if(destroyed)return;
      activeWorld=world.id;
      animateSelectedWorld(doc,b);
      worldFeedback.textContent='ОТКРЫТ ПОДРАЗДЕЛ · '+world.label+
        ' · действия ниже требуют отдельного подтверждения NOX';
      backWorld.hidden=false;refresh();
    });
    worldGrid.append(b);worldButtons.push({world,button:b});
  }
  backWorld.addEventListener('click',()=>{
    if(destroyed)return;activeWorld=null;backWorld.hidden=true;
    worldFeedback.textContent='Выберите подраздел';refresh();
  });
  const grid=make(doc,'div','nox-sb-grid');
  const sourceHub=make(doc,'section','nox-sb-sourcehub');
  sourceHub.dataset.noxSubview='selfbuilder-source-v1';
  const sourceTitle=make(doc,'h3','nox-sb-sourcehub__title','Самодописание ИИ · исходники и код');
  const codeIcon=p01Icon(doc,'code');if(codeIcon)sourceTitle.prepend(codeIcon);
  const sourceLead=make(doc,'p','nox-sb-subtitle','Один P02/S03. Исходники, модули, шаблоны, патчи и интеграции — только проверенные данные. Код сначала кандидат, затем согласование.');
  const sourceGrid=make(doc,'div','nox-sb-grid');
  const sourceStatus=make(doc,'p','nox-sb-feedback','Библиотека · ожидает проверки текущего Git HEAD');
  sourceStatus.setAttribute('role','status');sourceStatus.setAttribute('aria-live','polite');
  const sourceList=make(doc,'ul','nox-sb-sourcehub__list');
  sourceHub.append(sourceTitle,sourceLead,sourceGrid,sourceStatus,sourceList);
  const feedback=make(doc,'p','nox-sb-feedback','Ожидание состояния ядра · HOLD');
  feedback.setAttribute('role','status');feedback.setAttribute('aria-live','polite');
  const task=make(doc,'textarea','nox-sb-task');task.maxLength=3000;task.minLength=15;task.placeholder='Задача для локальной модели программиста';task.setAttribute('aria-label','Задача программисту');
  const jobs=make(doc,'select','nox-sb-job');jobs.setAttribute('aria-label','Подтверждённое задание FORGE');
  const buttons=[];let destroyed=false;const busy=new Set();
  function showSourceInventory(receipt){
    sourceList.replaceChildren();
    const items=Array.isArray(receipt?.items)?receipt.items:[];
    if(receipt?.status!=='SOURCE_INVENTORY_READ_ONLY'){
      sourceStatus.textContent='HOLD · '+(typeof receipt?.reason==='string'?receipt.reason:'Нет подтверждённого управляемого Git');
      return;
    }
    sourceStatus.textContent='Только чтение · '+items.length+' показано из '+receipt.supported_total+
      ' · допущено владельцем: '+receipt.owner_admitted_total+
      ' · S03 не заполняется без согласия';
    for(const item of items.slice(0,120)){
      if(typeof item?.path!=='string'||typeof item?.category!=='string')continue;
      const row=make(doc,'li','nox-sb-sourcehub__entry',
        item.category+' · '+item.path+(item.owner_admitted?' · OWNER SOURCE':' · REVIEW REQUIRED'));
      sourceList.append(row);
    }
  }
  for(const item of SELFBUILDER_MENU){
    const b=make(doc,'button','nox-sb-tile',item.label);b.type='button';
    if(item.actionId==='selfbuilder.worker.stop'){
      const stopIcon=p01Icon(doc,'stop');if(stopIcon)b.prepend(stopIcon);
    }b.dataset.routeId=item.routeId;
    b.dataset.actionId=item.actionId;b.dataset.section=item.section;
    const permitted=ownerApprovedRoute(item.section,item.routeId,item.actionId)===true;
    b.disabled=!permitted;b.dataset.state=permitted?'HOLD':'CONTRACT_REQUIRED';
    b.title=permitted?'Доступность зависит от действующего NOX':'Нет подтверждённого маршрута/обработчика';
    b.addEventListener('click',async()=>{
      if(destroyed||!permitted||b.disabled||busy.has(item.actionId))return;
      const current=getTrustedState(item.actionId);
      if(!current||current.available!==true){
        feedback.textContent='HOLD · '+item.label+' · нет подтверждённого обработчика';return;
      }
      if(item.actionId==='selfbuilder.propose'&&(!task.value?.trim()||task.value.trim().length<15||task.value.trim().length>3000)){feedback.textContent='HOLD · опишите задачу: от 15 до 3000 символов';task.focus();return;}
      const training=item.actionId.startsWith('training.')||item.actionId==='selfbuilder.train.request';
      if(training&&!jobs.value){feedback.textContent='HOLD · нет выбранного подтверждённого задания FORGE';return;}
      if(item.mode==='restricted'&&current.ownerConsent!==true&&current.requiresNativeConsent!==true){
        feedback.textContent='HOLD · для действия требуется разрешение владельца';return;
      }
      busy.add(item.actionId);b.disabled=true;b.dataset.state='PENDING';feedback.textContent='REQUESTED · '+item.label+' · ожидается ACK';
      try{
        const receipt=await invokeNative({routeId:item.routeId,actionId:item.actionId,source:'NOX_MENU_V2_OWNER',
             userGesture:true,...(training?{job_id:jobs.value}:{}),...(item.actionId==='selfbuilder.propose'?{task:task.value.trim()}:{} )});
        if(item.actionId==='selfbuilder.sources.inspect')showSourceInventory(receipt);
        feedback.textContent=receipt?.ack===true
          ?(item.mode==='read'?'ПОЛУЧЕНО · '+item.label:
             typeof receipt.run_id==='string'?'QUEUED · '+item.label+' · '+receipt.run_id:training?'ОТВЕТ FORGE · '+(receipt.status||'ПОЛУЧЕНО'):'HOLD · задача не принята')
          :'HOLD · '+(receipt?.errorCode||'нет подтверждённого ответа NOX');
      }catch(_){feedback.textContent='HOLD · ошибка соединения с ядром';}
      finally{busy.delete(item.actionId);if(!destroyed)refresh();}
    });
    (item.subview==='code'?sourceGrid:grid).append(b);buttons.push({b,item,permitted});
  }
  wrapper.append(heading,info,worldSection,task,jobs,grid,sourceHub,feedback);root.append(wrapper);
  function refresh(){
    const selected=jobs.value;const known=getTrainingJobs().filter(x=>typeof x?.id==='string'&&x.id.length>0);
    jobs.replaceChildren?.();
    const empty=make(doc,'option','',known.length?'Выберите задание FORGE':'Нет подтверждённых заданий FORGE');empty.value='';jobs.append(empty);
    for(const job of known){const option=make(doc,'option','',job.id+' · '+(job.status||'HOLD'));option.value=job.id;jobs.append(option);}
    jobs.value=known.some(x=>x.id===selected)?selected:'';
    const section=typeof getCurrentSection==='function'?getCurrentSection():null;
    if(activeWorld&&!P01_MENU_WORLD_NAV.some(w=>w.id===activeWorld&&w.section===section)){
      activeWorld=null;backWorld.hidden=true;worldFeedback.textContent='Выберите подраздел';
    }
    worldSection.hidden=section!==null&&!MENU_V2_SECTIONS.includes(section);
    const availableWorlds=menuWorldsForSection(section);
    for(const {world,button} of worldButtons){
      button.hidden=world.section!==section||(activeWorld!==null&&world.id!==activeWorld);
      button.setAttribute('aria-pressed',String(world.id===activeWorld));
    }
    worldHeading.textContent=activeWorld
      ?'Подраздел · '+(P01_MENU_WORLD_NAV.find(w=>w.id===activeWorld)?.label||'NOX')
      :'Подразделы NOX · '+availableWorlds.length;
    jobs.hidden=section!==null&&section!=='РАЗВИТИЕ';
    task.hidden=section!==null&&!['РАБОТА','РАЗВИТИЕ'].includes(section);
    sourceHub.hidden=section!==null&&section!=='РАЗВИТИЕ';
    for(const {b,item,permitted} of buttons){
      if(destroyed)return;
      b.hidden=typeof getCurrentSection==='function'&&getCurrentSection()!==item.section;
      const s=getTrustedState(item.actionId)||{};
      const allowed=permitted&&s.available===true&&(item.mode!=='restricted'||(s.ownerConsent===true||s.requiresNativeConsent===true));
      b.disabled=!allowed||busy.has(item.actionId);
      b.dataset.state=busy.has(item.actionId)?'PENDING':permitted?status(s.status||'HOLD'):'CONTRACT_REQUIRED';
      if(item.mode==='restricted'&&s.ownerConsent!==true)b.title='Требуется разрешение владельца';
    }
  }
  refresh();
  return Object.freeze({refresh,destroy:()=>{destroyed=true;wrapper.remove();}});
}
