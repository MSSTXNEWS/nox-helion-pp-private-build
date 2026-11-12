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
const isNative=()=>window.NOX_NATIVE_OWNER===true;
const hold=why=>'HOLD · '+String(why||'нет подтверждённых данных').slice(0,175);
const hex64=v=>typeof v==='string'&&/^[a-f0-9]{64}$/i.test(v);
const maxText=v=>String(v??'Н/Д').slice(0,100).replace(/[\x00-\x1f\x7f]/g,' ');
const validStatus=x=>x&&x.backend==='EXISTING_NATIVE_ONEHOST'&&x.native_p02_bound===true&&
  typeof x.primary_model==='string'&&x.primary_model.trim().length>0;
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
 if(!isNative())throw Error('требуется работающий локальный OneHost');
 const owner=await jsonRead('/api/nox/status');
 if(!validStatus(owner))throw Error('не подтверждена идентичность нативного OneHost/P02');
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
  const entries=['cpu_percent','gpu_percent','gpu_hotspot_c','ram_used_gb','vram_used_gb'].filter(k=>Number.isFinite(x[k]));
  return entries.length ? ['PC · ПОКАЗАНИЯ ONEHOST (НЕ GPU/SAFE70 ТЕСТ)',...entries.map(k=>k+': '+x[k])].join('\n'):
   hold('отсутствуют допустимые показания PC');
 }
 if(label==='PC · создатель'){
  const count=Array.isArray(x.items)?x.items.length:(Array.isArray(x.rows)?x.rows.length:null);
  return count===null?hold('события происхождения не подтверждены'):
   'PC · история создателя: '+count+' доступных событий по квитанции OneHost\nДетали — только в S03, без выдуманного рождения.';
 }
 if(label==='PC · эмоции')return typeof x.mood==='string'||typeof x.state==='string'?('PC · модель поведения: '+maxText(x.mood||x.state)+'\nНе означает субъективные чувства.'):
  hold('статус эмоционального регулятора не подтверждён');
 if(label==='PC MEMORY · S03')return (x.schema||x.status||x.state)?'PC MEMORY · статус S03: '+maxText(x.status||x.state||x.schema)+'\nДанные остаются в OneHost; отдельная база не создаётся.':hold('S03 не предоставила статус');
 if(label==='PC MEMORY · диалоги')return x.persistent_threads===true&&x.status==='READY'? 'PC MEMORY · диалоги подтверждены в S03 (по OneHost).\nИстория остаётся в основном «Резонансе».':hold('постоянные диалоги OneHost не подтверждены');
 return hold('нет данных '+label);
}
const actions={
 chat:[['pc-creator','PC · СОЗДАТЕЛЬ','/api/nox/creator?limit=12','PC · создатель'],
       ['pc-mood','PC · ЭМОЦИИ','/api/nox/mood','PC · эмоции'],
       ['pc-gpu','PC · РЕСУРСЫ','/api/nox/pc-load','PC · ресурс GPU'],
       ['s03-dialogs','S03 · ДИАЛОГИ','/api/ui/memory/dialogs/status','PC MEMORY · диалоги']],
 memory:[['pc-s03','PC MEMORY · S03','/api/ui/memory/status','PC MEMORY · S03'],
         ['s03-dialogs','PC MEMORY · ДИАЛОГИ','/api/ui/memory/dialogs/status','PC MEMORY · диалоги'],
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
