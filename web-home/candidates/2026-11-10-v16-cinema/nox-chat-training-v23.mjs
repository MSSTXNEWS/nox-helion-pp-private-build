/* NOX V23 — OneHost-only web chat / distillation evidence. No second backend,
   synthetic progress, alternate models, public API secrets or training autorun. */
export function assessChatTraining(owner={}, trainer={}, proof={}){
 const model=typeof owner.primary_model==='string'?owner.primary_model.trim():'';
 const ownerReady=owner.backend==='EXISTING_NATIVE_ONEHOST'&&owner.native_p02_bound===true&&
   owner.native_contract?.transport_bound===true&&model.length>0&&/^nox(?:[-_:]|$)/i.test(model);
 const valid=Number.isSafeInteger(trainer.controller_receipt?.actual_steps)&&
   trainer.controller_receipt.actual_steps>=0&&
   Number.isSafeInteger(trainer.controller_receipt?.requested_steps)&&
   trainer.controller_receipt.requested_steps>0&&
   trainer.controller_receipt.actual_steps<=trainer.controller_receipt.requested_steps;
 const coordinator=trainer.managed_coordinator_bound===true&&trainer.nox_training_identity_verified===true;
 const age=trainer.receipt_age_seconds;
 const recent=Number.isFinite(age)&&age>=0&&age<=15;
 const live=ownerReady&&coordinator&&recent&&valid&&
   trainer.gpu_admission?.lock_held===true&&trainer.gpu_admission.activity==='TRAINING'&&
   String(trainer.status).toLowerCase()==='running';
 const sha=proof.studentWeightsSha256;
 const checkpoint=ownerReady&&proof.schema==='nox-progress-receipt-v1'&&
   proof.operation==='FULL_WEIGHT_DISTILLATION'&&proof.model==='NOX'&&
   proof.attestation==='LOCAL_WEIGHT_AND_TRAINER_STATE_SHA256_CHECKED'&&
   proof.weightUpdateVerified===true&&
   (proof.status==='VERIFIED_CHECKPOINT_STEPS'||proof.status==='VERIFIED_COMPLETE')&&
   typeof sha==='string'&&/^[a-f0-9]{64}$/i.test(sha)&&
   Number.isSafeInteger(proof.completedSteps)&&proof.completedSteps>=0&&
   Number.isSafeInteger(proof.targetSteps)&&proof.targetSteps>0&&
   proof.completedSteps<=proof.targetSteps&&
   Number.isFinite(proof.stepPercent)&&Math.abs(proof.stepPercent-
   Number((100*proof.completedSteps/proof.targetSteps).toFixed(2)))<.005;
 return Object.freeze({
  ownerReady,model:ownerReady?model:null,coordinatorVerified:ownerReady&&coordinator,
  live,observedSteps:live?trainer.controller_receipt.actual_steps:null,
  observedTarget:live?trainer.controller_receipt.requested_steps:null,
  checkpointVerified:checkpoint,
  checkpointPercent:checkpoint?proof.stepPercent:null,
  checkpointSteps:checkpoint?proof.completedSteps:null,
  checkpointTarget:checkpoint?proof.targetSteps:null,
  checkpointSha:checkpoint?sha:null,
  windowsVerified:checkpoint&&proof.windowsSyncVerified===true,
  qualityVerified:checkpoint&&proof.qualityGainVerified===true,
  status:!ownerReady?'HOLD_ONEHOST_NOT_BOUND':!coordinator?'HOLD_TRAINER_NOT_VERIFIED':
    checkpoint?'VERIFIED_CHECKPOINT':live?'LIVE_TRAINER_UNVERIFIED_WEIGHTS':'HOLD_NO_VERIFIED_CHECKPOINT'
 });
}
function mount(){
 if(typeof document==='undefined'||typeof window==='undefined')return;
 if(document.body?.dataset.page!=='chat'||document.getElementById('nox-chat-training-v23'))return;
 const node=(tag,className,content)=>{const n=document.createElement(tag);if(className)n.className=className;if(content!==undefined)n.textContent=content;return n};
 const panel=node('section','nox-chat-training-v23');
 panel.id='nox-chat-training-v23';panel.setAttribute('aria-label','NOX: реальное обучение и проверка весов');
 const title=node('h3','','ОБУЧЕНИЕ И ДИСТИЛЛЯЦИЯ · NOX');
 const state=node('p','nox-chat-training-state','HOLD · проверка OneHost не выполнена');state.setAttribute('role','status');
 const steps=node('p','nox-chat-training-data','Шаги: Н/Д · собственные веса: не проверены');
 const proof=node('p','nox-chat-training-proof','Источник подтверждения: отсутствует');
 const controls=node('div','nox-chat-training-buttons');
 const refresh=node('button','', 'ПРОВЕРИТЬ РЕАЛЬНЫЙ ПРОГРЕСС');refresh.type='button';
 const training=node('a','','ОТКРЫТЬ ОБУЧЕНИЕ');training.href=window.NOX_NATIVE_OWNER===true?'/nox/training':'./training.html';
 controls.append(refresh,training);panel.append(title,state,steps,proof,controls);
 const dock=document.querySelector('.chat-command-dock')||document.querySelector('main');
 if(!dock)return;dock.prepend(panel);
 let busy=false;let last=null;
 async function get(path,timeout){
  const response=await fetch(path,{cache:'no-store',credentials:'same-origin',
   headers:{Accept:'application/json'},signal:AbortSignal.timeout(timeout)});
  if(!response.ok)throw Error(path+' HTTP '+response.status);
  if(!(response.headers.get('Content-Type')||'').toLowerCase().includes('json'))
   throw Error(path+' INVALID_CONTENT_TYPE');
  const value=await response.json();if(!value||typeof value!=='object')throw Error(path+' INVALID_BODY');
  return value;
 }
 async function check(){
  if(busy)return;busy=true;refresh.disabled=true;
  state.textContent='ПРОВЕРКА · читаю существующий OneHost…';
  try{
   if(window.NOX_NATIVE_OWNER!==true){
    last=assessChatTraining();
    state.textContent='HOLD · WEB без подтверждённого нативного OneHost';
    steps.textContent='Чат и запуск обучения недоступны до подтверждения владельца';
    proof.textContent='Статический preview не является работающим NOX';
    refresh.disabled=true;refresh.title='Нужен действующий OneHost; из WEB нельзя запускать новый GPU';
    return;
   }
   const [owner,trainer,evidence]=await Promise.allSettled([
    get('/api/nox/status',7000),get('/api/nox/training/status',7000),get('/api/nox/progress',7000)]);
   const ownerValue=owner.status==='fulfilled'?owner.value:{};
   const trainerValue=trainer.status==='fulfilled'?trainer.value:{};
   const proofValue=evidence.status==='fulfilled'?evidence.value:{};
   last=assessChatTraining(ownerValue,trainerValue,proofValue);
   state.textContent=last.ownerReady?
    (last.live?'NOX · ТРЕНЕР ПОДТВЕРЖДЁН, АКТИВЕН':last.coordinatorVerified?'NOX · КООРДИНАТОР ПОДТВЕРЖДЁН · LIVE НЕ ДОКАЗАН':'HOLD · ТРЕНЕР NOX НЕ ПОДТВЕРЖДЁН'):
    'HOLD · ONEHOST / СОБСТВЕННАЯ МОДЕЛЬ НЕ ПОДТВЕРЖДЕНЫ';
   steps.textContent=last.checkpointVerified?
    'СОБСТВЕННЫЕ ВЕСА: SHA-256 PASS · шаг '+last.checkpointSteps+'/'+last.checkpointTarget+' · '+last.checkpointPercent.toFixed(2)+'% подтверждённых шагов':
    last.live?'Текущие шаги контроллера: '+last.observedSteps+'/'+last.observedTarget+
     ' · обновление собственных весов пока HOLD':'Шаги и изменения весов: Н/Д (нет проверенного контрольного отчёта)';
   proof.textContent=last.checkpointVerified?
    'SHA: '+last.checkpointSha.slice(0,18)+'… · Windows '+(last.windowsVerified?'PASS':'HOLD')+
    ' · качество '+(last.qualityVerified?'PASS':'HOLD'):
    'Причина: '+last.status+' · GPU % не является прогрессом интеллекта';
   panel.dataset.status=last.status;
  }catch(err){
   last=null;state.textContent='HOLD · ОШИБКА ПРОВЕРКИ';
   steps.textContent='Данные не получены, старые проценты скрыты';
   proof.textContent=String(err.message||err).slice(0,180);
  }finally{busy=false;if(window.NOX_NATIVE_OWNER===true)refresh.disabled=false;}
 }
 refresh.addEventListener('click',check);
 if(window.NOX_NATIVE_OWNER===true){
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)void check()});
  window.addEventListener('nox-training-activity',()=>{if(!document.hidden)void check()});
  void check();
 }else{
  void check();
 }
 window.NOX_CHAT_TRAINING_V23=Object.freeze({refresh:check,last:()=>last,source:'EXISTING_ONEHOST_READ_ONLY'});
}
if(typeof window!=='undefined'){
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});
 else mount();
}
