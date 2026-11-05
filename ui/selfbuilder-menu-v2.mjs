/** NOX MENU V2 extension, mounted ONLY by the existing trusted WPF/WebView2 host.
 *  NO changes to HOME, original D02 assets, eight MENU tiles or eight CoreID.
 *  Receives verified native state and sends requests through the EXISTING host;
 *  no direct privileged bridge, simulated GPU training or autostart.
 */
import {LOGICAL_MENU_PARENTS} from '../proposals/P01/WOW-MAX10/scene-contract.mjs';
import {createNoxLucideIcon} from './nox-lucide-icons.mjs';
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
// Existing approved actions grouped ONLY in the rendered menu. No new
// action IDs, native approvals, scheduler or backend. All entries remain reachable.
export const NOX_NAV_GROUPS=Object.freeze([
 Object.freeze({id:'status',label:'ОБЗОР И СТАТУС'}),
 Object.freeze({id:'models',label:'МОДЕЛИ И ОЧЕРЕДЬ'}),
 Object.freeze({id:'weights',label:'ВЕСА И GPU'}),
 Object.freeze({id:'source',label:'ИСХОДНИКИ И КОД'}),
 Object.freeze({id:'control',label:'УПРАВЛЕНИЕ'})
]);
export function groupForNoxAction(item){
 const action=String(item?.actionId||'');
 if(action.endsWith('.stop'))return 'control';
 if(item?.subview==='code'||action==='selfbuilder.propose'||action.includes('.sources.'))return 'source';
 if(/^training\.|\.train\.request$|gpu/i.test(action))return 'weights';
 if(/model|seed|weight|learning|study|coding/i.test(action))return 'models';
 if(item?.mode==='restricted')return 'control';
 return 'status';
}
// One read-only, native capability dashboard: no downloads, code execution
// or weight modification. Reuse the existing OneHost/P02/S03 actions.
export const P01_READINESS_ACTIONS=Object.freeze([
  Object.freeze({action:'selfbuilder.capabilities',label:'Локальный ИИ и разрешения'}),
  Object.freeze({action:'selfbuilder.coding.models',label:'Установленные модели'}),
  Object.freeze({action:'selfbuilder.sources.inspect',label:'Исходники и интеграции'}),
  Object.freeze({action:'selfbuilder.worker.status',label:'Самодописание и задания'}),
  Object.freeze({action:'selfbuilder.learning.proofs',label:'Память S03 и подтверждённое обучение'})
]);
export function p01ReadinessResult(action,receipt){
  if(!P01_READINESS_ACTIONS.some(x=>x.action===action))
    return Object.freeze({state:'HOLD',message:'Неизвестная проверка'});
  if(receipt?.readVerified!==true)
    return Object.freeze({state:'HOLD',message:'Нет проверенного S03 ответа только для чтения'});
  if(action==='selfbuilder.capabilities'){
    const available=Object.values(receipt.actions||{}).filter(x=>x?.available===true).length;
    const configured=typeof receipt.source_head==='string' && /^[a-f0-9]{40,64}$/.test(receipt.source_head);
    const training=receipt.actions?.['selfbuilder.train.request']?.available===true;
    return Object.freeze({state:configured?'AVAILABLE':'HOLD',
      message:available+' нативных действий; Git HEAD '+(configured?'проверен':'не настроен')+
      '; QLoRA route '+(training?'настроен, обучение НЕ запущено':'HOLD — требуется одобренное GPU-задание')});
  }
  if(action==='selfbuilder.coding.models'){
    const n=Array.isArray(receipt.models)?receipt.models.length:0;
    return Object.freeze({state:n>0?'AVAILABLE':'HOLD',
      message:n+' локальных моделей обнаружено; наличие модели не равно обучению'});
  }
  if(action==='selfbuilder.sources.inspect'){
    const ok=receipt.status==='SOURCE_INVENTORY_READ_ONLY';
    const n=ok&&Number.isInteger(receipt.owner_admitted_total)?receipt.owner_admitted_total:0;
    return Object.freeze({state:ok?'AVAILABLE':'HOLD',
      message:ok?n+' источников допущено владельцем; импорт в S03 отдельно':
        'Нет проверенного управляемого Git-источника'});
  }
  if(action==='selfbuilder.worker.status'){
    const state=typeof receipt.status==='string'?receipt.status:'HOLD';
    const tasks=Array.isArray(receipt.tasks)?receipt.tasks.length:0;
    return Object.freeze({state:state==='READY_FOR_OWNER_TASK'?'AVAILABLE':'HOLD',
      message:tasks+' задач в S03; состояние '+state+'; автозапуск не выполнялся'});
  }
  const responded=receipt.status==='S03_READ'&&Array.isArray(receipt.tasks);
  const n=responded?receipt.tasks.length:0;
  return Object.freeze({state:responded?'AVAILABLE':'HOLD',
    message:n+' записей S03 с результатом; память '+(responded?'отвечает':'недоступна')+
      '; QUEUED/HOLD не доказывают обучение; веса не изменялись этим запросом'});
}
const VALID=new Set(['VERIFIED','RUNNING','IDLE','PAUSED','HOLD','OFFLINE','NOT_INSTALLED','ERROR','PENDING','AVAILABLE','NATIVE_REQUEST_AVAILABLE']);
function status(value){return VALID.has(value)?value:'HOLD';}
function make(doc,tag,cls,text){const x=doc.createElement(tag);if(cls)x.className=cls;if(text)x.textContent=text;return x;}
// Decorative icon geometry reuses the existing trusted UI and never changes
// button text/route/native consent. No extra controls or HOME overlays.
const NOX_WORLD_ICON=Object.freeze({
 work:'briefcase-business', intelligence:'brain',knowledge:'book-open',
 learning:'gauge',entertainment:'film',people:'heart',creative:'palette',
 business:'chart-line',world:'globe',pc:'monitor'
});
const NOX_GROUP_ICON=Object.freeze({
 status:'activity',models:'cpu',weights:'gauge',source:'code',control:'settings'
});
function decorateNoxIcon(doc,button,name){
 const icon=createNoxLucideIcon(doc,name);
 if(icon)button.prepend(icon);
 return button;
}
export function mountSelfBuilderMenuV2({root,invokeNative,getTrustedState,ownerApprovedRoute,documentRef,getCurrentSection,getTrainingJobs=()=>[],invokeP03Queue=null,invokeP03Cancel=null}){
  if(!root || typeof invokeNative!=='function' || typeof getTrustedState!=='function'||
     typeof ownerApprovedRoute!=='function')throw Error('NOX_NATIVE_MENU_HOST_REQUIRED');
  const doc=documentRef||root.ownerDocument;
  if(!doc)throw Error('DOM_REQUIRED');
  if(root.dataset?.noxPage==='home'||root.closest?.('[data-nox-page="home"]'))throw Error('D02_HOME_LOCK');
  if(root.querySelector?.('[data-nox-selfbuilder="v2"]'))throw Error('DUPLICATE_MENU_EXTENSION');
  const wrapper=make(doc,'section','nox-sb-panel');wrapper.dataset.noxSelfbuilder='v2';
  wrapper.classList.add('nox-fx');
  const smoke=make(doc,'img','nox-fx-smoke');
  smoke.src=new URL('./fx/smoke.svg', import.meta.url).href;
  smoke.alt='';
  smoke.setAttribute('aria-hidden','true');
  const canvas=make(doc,'canvas','nox-fx-canvas');
  canvas.setAttribute('aria-hidden','true');
  wrapper.prepend(canvas, smoke);
  if (globalThis.THREE) {
    import('./fx/nox-wow-scene.js').then(m => m.mountNoxWow(canvas)).catch(()=>{});
  }
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
  decorateNoxIcon(doc,backWorld,'arrow-left');
  backWorld.type='button';backWorld.hidden=true;
  const path=make(doc,'nav','nox-sb-nav-path');
  path.setAttribute('aria-label','Путь NOX: направление, страница, подраздел');
  const groupHeading=make(doc,'h3','nox-sb-sourcehub__title','Группы действий');
  const groupGrid=make(doc,'div','nox-sb-grid nox-sb-group-grid');
  const backGroup=make(doc,'button','nox-sb-tile','← Подразделы');backGroup.type='button';backGroup.hidden=true;
  decorateNoxIcon(doc,backGroup,'arrow-left');
  worldSection.append(worldHeading,path,worldGrid,backWorld,groupHeading,groupGrid,backGroup,worldFeedback);
  let activeWorld=null,activeGroup=null;
  const worldButtons=[];
  for(const world of P01_MENU_WORLD_NAV){
    const b=make(doc,'button','nox-sb-tile',world.label);
    b.type='button';b.dataset.noxWorld=world.id;b.dataset.noxWorldParent=world.section;
    b.addEventListener('click',()=>{
      if(destroyed)return;
      activeWorld=world.id;activeGroup=null;
      worldFeedback.textContent='ОТКРЫТ ПОДРАЗДЕЛ · '+world.label+
        ' · действия ниже требуют отдельного подтверждения NOX';
      backWorld.hidden=false;refresh();
    });
    decorateNoxIcon(doc,b,NOX_WORLD_ICON[world.id]);
    worldGrid.append(b);worldButtons.push({world,button:b});
  }
  backWorld.addEventListener('click',()=>{
    if(destroyed)return;activeWorld=null;activeGroup=null;backWorld.hidden=true;
    worldFeedback.textContent='Выберите подраздел';refresh();
  });
  backGroup.addEventListener('click',()=>{
    if(destroyed)return;activeGroup=null;refresh();
  });
  const grid=make(doc,'div','nox-sb-grid');
  const sourceHub=make(doc,'section','nox-sb-sourcehub');
  sourceHub.dataset.noxSubview='selfbuilder-source-v1';
  const sourceTitle=make(doc,'h3','nox-sb-sourcehub__title','Самодописание ИИ · исходники и код');
  const sourceLead=make(doc,'p','nox-sb-subtitle','Один P02/S03. Исходники, модули, шаблоны, патчи и интеграции — только проверенные данные. Код сначала кандидат, затем согласование.');
  const sourceGrid=make(doc,'div','nox-sb-grid');
  const sourceStatus=make(doc,'p','nox-sb-feedback','Библиотека · ожидает проверки текущего Git HEAD');
  sourceStatus.setAttribute('role','status');sourceStatus.setAttribute('aria-live','polite');
  const sourceList=make(doc,'ul','nox-sb-sourcehub__list');
  const diagnostic=make(doc,'button','nox-sb-tile','Проверить локальный ИИ · память · модели · исходники');
  diagnostic.type='button';diagnostic.dataset.noxReadiness='native-only';
  const diagnosticList=make(doc,'ul','nox-sb-sourcehub__list');
  diagnosticList.setAttribute('aria-label','Результаты проверки локального ИИ');
  const queueButton=make(doc,'button','nox-sb-tile','Проверить очередь моделей · P03');
  queueButton.type='button';queueButton.dataset.noxP03Queue='native-only';
  queueButton.disabled=typeof invokeP03Queue!=='function';
  queueButton.dataset.state=queueButton.disabled?'HOLD':'IDLE';
  const queueStatus=make(doc,'p','nox-sb-feedback','P03 · ожидание native ACK');
  queueStatus.setAttribute('role','status');queueStatus.setAttribute('aria-live','polite');
  const queueStops=make(doc,'div','nox-sb-grid');queueStops.dataset.noxP03StopList='native-only';
  sourceHub.append(sourceTitle,sourceLead,diagnostic,diagnosticList,queueButton,queueStatus,queueStops,sourceGrid,sourceStatus,sourceList);
  const feedback=make(doc,'p','nox-sb-feedback','Ожидание состояния ядра · HOLD');
  feedback.setAttribute('role','status');feedback.setAttribute('aria-live','polite');
  const task=make(doc,'textarea','nox-sb-task');task.maxLength=3000;task.minLength=15;task.placeholder='Задача для локальной модели программиста';task.setAttribute('aria-label','Задача программисту');
  const jobs=make(doc,'select','nox-sb-job');jobs.setAttribute('aria-label','Подтверждённое задание FORGE');
  const buttons=[];let destroyed=false;let diagnosticBusy=false;let queueBusy=false;const busy=new Set();
  let queueViewEpoch=0;
  queueButton.addEventListener('click',async()=>{
    if(destroyed||queueBusy||typeof invokeP03Queue!=='function')return;
    const epoch=++queueViewEpoch;
    queueBusy=true;queueButton.disabled=true;queueButton.dataset.state='PENDING';
    queueStops.replaceChildren();
    queueStatus.textContent='REQUESTED · P03 · ожидается native ACK';
    try{
      const receipt=await invokeP03Queue();
      if(destroyed||epoch!==queueViewEpoch)return;
      if(receipt?.ack!==true||!Array.isArray(receipt.jobs)){
        queueStatus.textContent='HOLD · P03 · '+(receipt?.errorCode||'NATIVE_QUEUE_UNAVAILABLE');return;
      }
      queueStatus.textContent='P03 · '+receipt.jobs.length+' заданий · STOP только по native ACK';
      if(typeof invokeP03Cancel!=='function')return;
      const seen=new Set();
      for(const job of receipt.jobs.slice(0,16)){
        const jobId=job?.id;
        if(typeof jobId!=='string'||!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(jobId)||
           seen.has(jobId)||!['queued','running','downloading'].includes(String(job.state).toLowerCase()))continue;
        seen.add(jobId);
        const stop=make(doc,'button','nox-sb-tile','STOP · '+jobId);
        stop.type='button';stop.dataset.noxP03Stop=jobId;stop.dataset.state='IDLE';
        stop.addEventListener('click',async()=>{
          if(destroyed||stop.disabled)return;
          const stopEpoch=queueViewEpoch;
          stop.disabled=true;stop.dataset.state='PENDING';
          queueStatus.textContent='STOP REQUESTED · P03 · ожидается native ACK';
          try{
            const result=await invokeP03Cancel(jobId);
            if(destroyed||stopEpoch!==queueViewEpoch)return;
            if(result?.ack===true&&result.state==='STOP_REQUESTED'){
              stop.dataset.state='STOP_REQUESTED';
              queueStatus.textContent='STOP REQUESTED · '+jobId+' · обновите очередь для проверки';
            }else{
              stop.disabled=false;stop.dataset.state='HOLD';
              queueStatus.textContent='HOLD · P03 STOP · '+(result?.errorCode||'NATIVE_STOP_UNVERIFIED');
            }
          }catch(_){if(!destroyed&&stopEpoch===queueViewEpoch){
            stop.disabled=false;stop.dataset.state='HOLD';queueStatus.textContent='HOLD · P03 STOP · нет ACK';
          }}
        });
        queueStops.append(stop);
      }
    }catch(_){if(!destroyed&&epoch===queueViewEpoch)queueStatus.textContent='HOLD · P03 · native не ответил';}
    finally{queueBusy=false;if(!destroyed){queueButton.disabled=false;queueButton.dataset.state='IDLE';}}
  });
  // Zero download / zero new agent: owner-approved task primers feed the existing
  // SELF-BUILDER proposer after a separate explicit click and native consent.
  const taskPresets=Object.freeze([
    Object.freeze({label:'Подготовить улучшение MENU / WOW',task:
      'Проверь подтверждённые источники текущего Git HEAD для существующего NOX HELION EXPRESS INTEGRATOR. Предложи ровно один минимальный обратимый патч MENU/D02/WOW/кнопок с тестом и SHA, сохрани исходную графику и native consent. Ничего не устанавливай и не объединяй автоматически.'}),
    Object.freeze({label:'Подготовить самоулучшение кода',task:
      'Изучи только проверенные исходники текущего HEAD и подтверждённые ошибки существующего загрузчика NOX HELION EXPRESS INTEGRATOR. Подготовь один безопасный кандидат кода в изолированной папке с тестом, откатом и источниками. Не изменяй основной EXE и не повышай статус без приёмки.'})
  ]);
  for(const preset of taskPresets){
    const button=make(doc,'button','nox-sb-tile',preset.label);button.type='button';
    button.dataset.noxOwnerTaskPreset='true';
    button.addEventListener('click',()=>{
      if(destroyed)return;
      task.value=preset.task;task.focus();
      feedback.textContent='Задача подготовлена. Запуск — только отдельной кнопкой «Создать кандидат кода» с нативным согласием.';
    });
    sourceGrid.append(button);
  }
  diagnostic.addEventListener('click',async()=>{
    if(destroyed||diagnosticBusy)return;
    diagnosticBusy=true;diagnostic.disabled=true;diagnostic.dataset.state='PENDING';
    diagnosticList.replaceChildren();
    sourceStatus.textContent='REQUESTED · опрос существующего нативного ядра';
    try{
      // Sequential, bounded existing commands; never invent an extra provider,
      // grant, background agent, model download or a training run.
      for(const check of P01_READINESS_ACTIONS){
        if(destroyed)break;
        let receipt;
        try{receipt=await invokeNative({routeId:'evolution',actionId:check.action,
          source:'NOX_MENU_V2_OWNER',userGesture:true});}
        catch(_){receipt={ack:false};}
        if(destroyed)break;
        const result=p01ReadinessResult(check.action,receipt);
        const item=make(doc,'li','nox-sb-sourcehub__entry',
          check.label+' · '+result.state+' · '+result.message);
        item.dataset.state=result.state;diagnosticList.append(item);
      }
      if(!destroyed)sourceStatus.textContent='Проверка окончена · функции доступны только с native ACK';
    }finally{
      diagnosticBusy=false;
      if(!destroyed){diagnostic.disabled=false;diagnostic.dataset.state='IDLE';}
    }
  });
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
    const b=make(doc,'button','nox-sb-tile',item.label);b.type='button';b.dataset.routeId=item.routeId;
    decorateNoxIcon(doc,b,NOX_GROUP_ICON[groupForNoxAction(item)]);
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
        // A verified read is not an owner action ACK or learning receipt.
        const accepted=item.mode==='read'?receipt?.readVerified===true:receipt?.ack===true;
        feedback.textContent=accepted
          ?(item.mode==='read'?'ПРОЧИТАНО · '+item.label+' · не доказательство обучения':
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
      activeWorld=null;activeGroup=null;backWorld.hidden=true;
      worldFeedback.textContent='Выберите страницу';
    }
    const availableWorlds=menuWorldsForSection(section);
    worldSection.hidden=section!==null&&!MENU_V2_SECTIONS.includes(section);
    for(const {world,button} of worldButtons){
      button.hidden=world.section!==section;
      button.setAttribute('aria-pressed',String(world.id===activeWorld));
    }
    worldGrid.hidden=activeWorld!==null;
    worldGrid.style.display=activeWorld===null?'':'none';
    backWorld.hidden=activeWorld===null;
    worldHeading.textContent=activeWorld
      ?'Страница · '+(P01_MENU_WORLD_NAV.find(w=>w.id===activeWorld)?.label||'NOX')
      :'Страницы направления · '+availableWorlds.length;
    path.replaceChildren();
    const mark=(title,current)=>{
      const crumb=make(doc,'span',current?'nox-sb-crumb-current':'nox-sb-crumb',title);
      if(current)crumb.setAttribute('aria-current','page');
      path.append(crumb);
    };
    mark(section||'HELION',!activeWorld);
    if(activeWorld){mark(P01_MENU_WORLD_NAV.find(w=>w.id===activeWorld)?.label||activeWorld,!activeGroup);}
    if(activeGroup){mark(NOX_NAV_GROUPS.find(g=>g.id===activeGroup)?.label||activeGroup,true);}
    groupGrid.replaceChildren();
    const available=SELFBUILDER_MENU.filter(item=>item.section===section);
    if(activeWorld){
      for(const group of NOX_NAV_GROUPS){
        const count=available.filter(item=>groupForNoxAction(item)===group.id).length;
        if(!count)continue;
        const button=make(doc,'button','nox-sb-tile nox-sb-group-tile',
          group.label+' · '+count);
        button.type='button';
        button.dataset.noxActionGroup=group.id;
        button.setAttribute('aria-pressed',String(activeGroup===group.id));
        button.addEventListener('click',()=>{if(destroyed)return;activeGroup=group.id;refresh();});
        decorateNoxIcon(doc,button,NOX_GROUP_ICON[group.id]);
        groupGrid.append(button);
      }
    }
    groupHeading.hidden=!activeWorld||!!activeGroup;
    groupGrid.hidden=!activeWorld||!!activeGroup;
    groupGrid.style.display=activeWorld&&!activeGroup?'':'none';
    backGroup.hidden=!activeGroup;
    grid.hidden=!activeGroup;
    grid.style.display=activeGroup?'':'none';
    jobs.hidden=section!=='РАЗВИТИЕ'||!['models','weights'].includes(activeGroup);
    task.hidden=activeGroup!=='source'||!['РАБОТА','РАЗВИТИЕ'].includes(section);
    sourceHub.hidden=activeGroup!=='source'||section!=='РАЗВИТИЕ';
    for(const {b,item,permitted} of buttons){
      if(destroyed)return;
      b.hidden=item.section!==section||!activeGroup||groupForNoxAction(item)!==activeGroup;
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
