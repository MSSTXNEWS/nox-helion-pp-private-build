/** NOX MENU V2 extension, mounted ONLY by the existing trusted WPF/WebView2 host.
 *  NO changes to HOME, original D02 assets, eight MENU tiles or eight CoreID.
 *  Receives verified native state and sends requests through the EXISTING host;
 *  no direct privileged bridge, simulated GPU training or autostart.
 */
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
  {section:'РАБОТА',routeId:'progress',label:'Проверенные улучшения',actionId:'selfbuilder.worker.status',mode:'read'}
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
  const grid=make(doc,'div','nox-sb-grid');const feedback=make(doc,'p','nox-sb-feedback','Ожидание состояния ядра · HOLD');
  feedback.setAttribute('role','status');feedback.setAttribute('aria-live','polite');
  const task=make(doc,'textarea','nox-sb-task');task.maxLength=3000;task.minLength=15;task.placeholder='Задача для локальной модели программиста';task.setAttribute('aria-label','Задача программисту');
  const jobs=make(doc,'select','nox-sb-job');jobs.setAttribute('aria-label','Подтверждённое задание FORGE');
  const buttons=[];let destroyed=false;const busy=new Set();
  for(const item of SELFBUILDER_MENU){
    const b=make(doc,'button','nox-sb-tile',item.label);b.type='button';b.dataset.routeId=item.routeId;
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
        feedback.textContent=receipt?.ack===true
          ?(item.mode==='read'?'ПОЛУЧЕНО · '+item.label:
             typeof receipt.run_id==='string'?'QUEUED · '+item.label+' · '+receipt.run_id:training?'ОТВЕТ FORGE · '+(receipt.status||'ПОЛУЧЕНО'):'HOLD · задача не принята')
          :'HOLD · '+(receipt?.errorCode||'нет подтверждённого ответа NOX');
      }catch(_){feedback.textContent='HOLD · ошибка соединения с ядром';}
      finally{busy.delete(item.actionId);if(!destroyed)refresh();}
    });
    grid.append(b);buttons.push({b,item,permitted});
  }
  wrapper.append(heading,info,task,jobs,grid,feedback);root.append(wrapper);
  function refresh(){
    const selected=jobs.value;const known=getTrainingJobs().filter(x=>typeof x?.id==='string'&&x.id.length>0);
    jobs.replaceChildren?.();
    const empty=make(doc,'option','',known.length?'Выберите задание FORGE':'Нет подтверждённых заданий FORGE');empty.value='';jobs.append(empty);
    for(const job of known){const option=make(doc,'option','',job.id+' · '+(job.status||'HOLD'));option.value=job.id;jobs.append(option);}
    jobs.value=known.some(x=>x.id===selected)?selected:'';
    jobs.hidden=typeof getCurrentSection==='function'&&getCurrentSection()!=='РАЗВИТИЕ';
    task.hidden=typeof getCurrentSection==='function'&&getCurrentSection()!=='РАБОТА';
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
