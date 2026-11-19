/* NOX WEB V29 — PC V25 capability integration inside the existing V27 pages.
 * Never creates another chat, a memory database, model or server.
 * Only same-origin READ operations against the existing verified OneHost.
 * No trusted host => HOLD; no invented progress, birth or S03 contents.
 */
const SCHEMA = 'nox-genesis-live-evidence-v1';
const PROGRESS = 'nox-progress-receipt-v1';
const PAGE = document.body?.dataset?.page;
const PAGES = new Set(['chat','memory','training']);
const $ = (name,cls='',value='') => {const n=document.createElement(name);if(cls)n.className=cls;if(value)n.textContent=value;return n};
const isNative=()=>window.NOX_NATIVE_OWNER===true||(
  location.protocol==='http:'&&['127.0.0.1','localhost','[::1]'].includes(location.hostname)&&location.port==='8766');
const hold=why=>'HOLD · '+String(why||'нет подтверждённых данных').slice(0,175);
const hex64=v=>typeof v==='string'&&/^[a-f0-9]{64}$/i.test(v);
const maxText=v=>String(v??'Н/Д').slice(0,100).replace(/[\x00-\x1f\x7f]/g,' ');
const validStatus=x=>x&&typeof x.primary_model==='string'&&x.primary_model.trim().length>0&&(
  (x.backend==='EXISTING_NATIVE_ONEHOST'&&x.native_p02_bound===true)||
  (x.host==='NOX_CHAT_V24.1'&&['READY','HOLD'].includes(x.status)&&
    typeof x.ollama==='string'&&typeof x.safe70==='object'&&x.safe70!==null));
function genesisUrl(){
 const raw=document.querySelector('meta[name="nox-genesis-evidence-endpoint"]')?.getAttribute('content');
 if(!raw||!/^\/api\/[a-z0-9_\-/]+$/i.test(raw)||raw.startsWith('//'))return null;
 try{const u=new URL(raw,location.origin);return u.origin===location.origin?u.pathname:null}catch{return null}
}
async function jsonRead(path){
 if(!/^\/api\/[a-z0-9_/?=&-]+$/i.test(path)||path.startsWith('//'))throw Error('недопустимый локальный маршрут');
 const c=new AbortController(),timer=setTimeout(()=>c.abort(),6500);
 try{
  const r=await fetch(path,{credentials:'same-origin',cache:'no-store',redirect:'error',signal:c.signal,headers:{Accept:'application/json'}});
  if(!r.ok)throw Error('OneHost HTTP '+r.status);
  if(!(r.headers.get('content-type')||'').toLowerCase().includes('application/json'))throw Error('ответ не JSON');
  if(Number(r.headers.get('content-length')||0)>250000)throw Error('слишком большой ответ');
  const text=await r.text();if(text.length>250000)throw Error('слишком большой ответ');
  const data=JSON.parse(text);if(!data||typeof data!=='object'||Array.isArray(data))throw Error('неподтверждённая схема');
  return data;
 }finally{clearTimeout(timer)}
}
async function authorized(){
 if(!isNative())throw Error('доступ только через локальный PC сервер :8766 или проверенный OneHost');
 const owner=await jsonRead('/api/nox/status');
 if(!validStatus(owner))throw Error('не подтверждена идентичность локального PC сервера или OneHost');
 return owner;
}
function formatProgress(p){
 if(!p||p.schema!==PROGRESS)return hold('неизвестный формат доказательств');
 if(p.status==='HOLD')return hold(p.reason||'нет подтверждённого checkpoint');
 if(!['VERIFIED_CHECKPOINT_STEPS','VERIFIED_COMPLETE'].includes(p.status)||!hex64(p.studentWeightsSha256)||
    !Number.isSafeInteger(p.completedSteps)||!Number.isSafeInteger(p.targetSteps)||p.completedSteps<0||
    p.targetSteps<=0||p.completedSteps>p.targetSteps||p.weightUpdateVerified!==true)
    return hold('недостаточно фактов об изменении собственных весов');
 return [
  'ПОЛУЧЕНА КВИТАНЦИЯ ОТ ONEHOST (НЕ НЕЗАВИСИМЫЙ GPU PASS)',
  'Модель: '+maxText(p.model||'NOX'),
  'Шаги: '+p.completedSteps+'/'+p.targetSteps,
  'Собственные веса SHA256: '+p.studentWeightsSha256,
  'Windows sync: '+(p.windowsSyncVerified===true?'по квитанции':'HOLD'),
  'Независимая оценка качества: '+(p.qualityGainVerified===true?'по квитанции':'HOLD'),
  'Рождение NOX PRIME: не определяется по одному этому API'
 ].join('\n');
}
function formatGenesis(x){
 if(!x||x.schema!==SCHEMA)return hold('GENESIS: схема источника не совпала');
 if(x.state==='HOLD')return hold(x.reason||'данные отсутствуют');
 if(x.state!=='RECEIPT_FORMAT_VALIDATED_NOT_GPU_REPLAYED'||!hex64(x.training?.model_sha256))
  return hold('GENESIS не подтвердил SHA весов или состояние квитанции');
 const t=x.training;
 return ['GENESIS · квитанция ONEHOST, НЕ аппаратная GPU-приёмка',
  'NOX SHA256: '+t.model_sha256,
  'Шаги optimizer (заявленные): '+(Number.isSafeInteger(t.optimizer_steps_claimed)?t.optimizer_steps_claimed:'HOLD'),
  'Checkpoint SHA: '+(hex64(t.checkpoint_sha256)?t.checkpoint_sha256:'HOLD'),
  'S03 readback: '+(x.memory?.state==='CONNECTED_BY_TRUSTED_HOST'?'по квитанции OneHost':'HOLD'),
  'Independent physical GPU acceptance: HOLD'].join('\n');
}
function formatOwner(label,x){
 if(!x||x.status==='HOLD'||x.state==='HOLD')return hold(x?.reason||'нет подтверждённых данных '+label);
 if(label==='PC · ресурс GPU'){
  const metrics=[
   ['CPU, %','cpu_load_percent'],['GPU, %','gpu_load_percent'],
   ['GPU Hot Spot, °C','gpu_hot_spot_c'],['RAM, ГБ','ram_used_gb'],
   ['VRAM, ГБ','vram_used_gb']
  ].filter(([,key])=>Number.isFinite(x[key]));
  if(!metrics.length)return hold('датчики CPU/GPU не дали достоверных значений');
  const result=['PC · ФАКТИЧЕСКИЕ ДАТЧИКИ · '+maxText(x.source||'НЕИЗВЕСТНЫЙ ИСТОЧНИК')];
  for(const [title,key] of metrics)result.push(title+': '+x[key]);
  result.push('SAFE70: '+(Number.isFinite(x.gpu_hot_spot_c)&&x.gpu_hot_spot_c>0?'показание получено; контроль порогов отдельно':'HOLD · отсутствует Hot Spot'));
  result.push('Независимая аппаратная приёмка: НЕ ПРОВЕДЕНА');
  return result.join('\n');
 }
 if(label==='PC · создатель'){
  if(x.status!=='READY'||!Array.isArray(x.messages)||!Number.isSafeInteger(x.total))
   return hold('список событий создателя не получен');
  const items=x.messages.slice(0,3).map(item=>
    '• '+maxText(item.created_at||'время не указано')+
    ' · SHA '+(hex64(item.sha256)?item.sha256.slice(0,12)+'…':'не указан'));
  return ['PC · СОЗДАТЕЛЬ · СООБЩЕНИЯ ИЗ СУЩЕСТВУЮЩЕЙ БАЗЫ',
    'Всего: '+x.total,...items,
    'Дата рождения PRIME определяется только в GENESIS Ledger'].join('\n');
 }
 if(label==='PC · эмоции'){
  if(x.status!=='READY'||typeof x.mood!=='string')return hold('регулятор эмоций недоступен');
  return 'PC · эмоциональная модель: '+maxText(x.mood)+
    '\nТип: '+(x.simulated===true?'симуляция поведения':'режим не подтверждён')+
    '\nЭто не утверждение о субъективных чувствах.';
 }
 if(label==='PC MEMORY · S03'){
  if(x.status!=='READY'||!x.stats||typeof x.stats!=='object'||!x.segments||typeof x.segments!=='object')
   return hold('S03 не вернула текущую структуру памяти');
  const keys=Object.keys(x.stats).slice(0,12);
  const lines=['PC · ПАМЯТЬ S03 · ДАННЫЕ ДЕЙСТВУЮЩЕГО СЕРВЕРА',
    'Genesis Ledger: '+(x.ledger_chain_ok===true?'целостность по API подтверждена':'HOLD · целостность не подтверждена')];
  for(const key of keys){
   const v=x.stats[key];
   if(typeof v==='number'||typeof v==='string')lines.push(maxText(key)+': '+maxText(v));
  }
  lines.push('Перезапуск и сохранность S03: НЕ ПРОВЕРЕНЫ');
  return lines.join('\n');
 }
 if(label==='PC MEMORY · диалоги'){
  if(x.status!=='READY'||!Array.isArray(x.dialogs))return hold('история диалогов не подтверждена');
  return ['PC MEMORY · ИСТОРИЯ НА ТЕКУЩЕМ СЕРВЕРЕ',
    'Диалогов: '+x.dialogs.length,
    'Сообщений: '+x.dialogs.reduce((n,d)=>n+(Number.isFinite(d.messages)?d.messages:0),0),
    'Непрерывность после рестарта: НЕ ПРОВЕРЕНА'].join('\n');
 }
 return hold('нет подтверждённых данных '+label);
}
const actions={
 chat:[['pc-creator','PC · СОЗДАТЕЛЬ','/api/nox/creator?limit=12','PC · создатель'],
       ['pc-mood','PC · ЭМОЦИИ','/api/nox/mood','PC · эмоции'],
       ['pc-gpu','PC · РЕСУРСЫ','/api/nox/pc-load','PC · ресурс GPU'],
       ['s03-dialogs','S03 · ДИАЛОГИ','/api/nox/history','PC MEMORY · диалоги']],
 memory:[['pc-s03','PC MEMORY · S03','/api/nox/memory','PC MEMORY · S03'],
         ['s03-dialogs','PC MEMORY · ДИАЛОГИ','/api/nox/history','PC MEMORY · диалоги'],
         ['pc-creator','PC · СОЗДАТЕЛЬ','/api/nox/creator?limit=12','PC · создатель']],
 training:[['pc-gpu','PC · РЕСУРСЫ','/api/nox/pc-load','PC · ресурс GPU']]
};
function boot(){
 if(!PAGES.has(PAGE)||document.querySelector('#nox-v29-addons'))return;
 const area=$('section','nox-v29-addons');area.id='nox-v29-addons';area.setAttribute('aria-label','NOX · дополнительные инструменты PC и GENESIS');
 area.append($('div','nox-v29-heading','NOX · РАСШИРЕННЫЕ ИНСТРУМЕНТЫ PC / GENESIS'));
 const tip=$('p','nox-v29-tip','Один «Резонанс» и одна S03. Дополнения работают только с проверенным OneHost.');area.append(tip);
 const row=$('div','nox-v29-actions');area.append(row);
 const panel=$('section','nox-v29-output');panel.hidden=true;panel.setAttribute('aria-live','polite');panel.setAttribute('role','status');
 const status=$('pre','nox-v29-result',hold('выберите функцию'));panel.append(status);
 const dismiss=$('button','nox-v29-button','СКРЫТЬ');dismiss.type='button';dismiss.addEventListener('click',()=>{panel.hidden=true;});panel.append(dismiss);area.append(panel);
 let seq=0,requested=0,lastResult='HOLD';
 async function show(id,path,label){
  panel.hidden=false;const current=++seq;requested++;lastResult='HOLD';status.textContent=hold('проверка локального OneHost…');
  try{await authorized();const data=await jsonRead(path);if(current!==seq)return;lastResult=data.status==='HOLD'?'HOLD':'RECEIPT';status.textContent=formatOwner(label,data);}catch(error){if(current===seq){lastResult='HOLD';status.textContent=hold(error.message);}}
 }
 for(const [id,title,path,label] of actions[PAGE]){
  const button=$('button','nox-v29-button',title);button.type='button';button.dataset.noxPcAction=id;
  button.addEventListener('click',()=>void show(id,path,label));row.append(button);
 }
 // Memory already has a real document reader/search: bring it into view, not a duplicate PC UI.
 if(PAGE==='memory'){
  const docs=$('button','nox-v29-button','PC MEMORY · ДОКУМЕНТЫ');docs.type='button';docs.dataset.noxPcAction='documents';
  docs.addEventListener('click',()=>{const target=document.querySelector('.nox-document-panel')||document.querySelector('#noxSourceGraphShow')||document.querySelector('[data-action="s03-search"]');
   if(target){target.scrollIntoView({behavior:'auto',block:'start'});target.querySelector('button,input')?.focus();}else{panel.hidden=false;status.textContent=hold('в этом источнике нет ридера документов');}});row.append(docs);
 }
 const genesis=$('button','nox-v29-button','GENESIS · ДОКАЗАТЕЛЬСТВА');genesis.type='button';genesis.dataset.noxPcAction='genesis';
 genesis.addEventListener('click',async()=>{
  panel.hidden=false;const current=++seq;requested++;status.textContent=hold('проверяю источник GENESIS и OneHost');
  try{
   await authorized();const trusted=genesisUrl();
   const data=await jsonRead(trusted||'/api/nox/progress');if(current!==seq)return;
   status.textContent=trusted?formatGenesis(data):formatProgress(data);
   lastResult=status.textContent.startsWith('HOLD')?'HOLD':'RECEIPT_NOT_GPU_REPLAYED';
  }catch(error){if(current===seq){status.textContent=hold(error.message);lastResult='HOLD';}}
 });row.append(genesis);
 const target=document.querySelector('main')||document.querySelector('.shell')||document.body;
 target.prepend(area);
 window.NOX_WEB_V29_ADDONS=Object.freeze({diagnostics:()=>({schema:'nox-web-v29-addons-v1',page:PAGE,source:'V27-primary-PC25-addons',trustedNative:isNative(),hasConfirmedGenesisMeta:!!genesisUrl(),buttons:row.querySelectorAll('button').length,requested,receiptStatus:lastResult,liveGpuAccepted:false})});
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
