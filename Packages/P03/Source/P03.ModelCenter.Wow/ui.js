/* NOX P03 MICRO-WOW: pure presentation, no network access, no fake device readings.
 * Host sends p03.snapshot.v1 / p03.event.v1 / p03.command.ack.v1 via WebView2.
 * WebView sends only p03.command.v1 after direct user gesture and capability check.
 */
'use strict';
const $ = id => document.getElementById(id);
const familySeed = [["deepseek-r1","DeepSeek R1"],["llama3.1","Llama 3.1"],["llama3.2","Llama 3.2"],["qwen2.5","Qwen 2.5"],["qwen3","Qwen 3"],["gemma3","Gemma 3"],["gemma2","Gemma 2"],["mistral","Mistral"],["llama3","Llama 3"],["qwen2.5-coder","Qwen 2.5 Coder"],["phi3","Phi 3"],["mxbai-embed-large","Mixedbread Embed Large"],["llava","LLaVA"],["gpt-oss","GPT-OSS"],["qwen3-coder","Qwen 3 Coder"],["qwen3-vl","Qwen 3 VL"],["tinyllama","TinyLlama"],["qwen2","Qwen 2"],["mistral-nemo","Mistral Nemo"],["yi-coder","Yi Coder"],["nous-hermes2","Nous Hermes 2"],["aya","Aya 23"],["stable-code","Stable Code"],["wizard-math","Wizard Math"],["llama-guard3","Llama Guard 3"],["internlm2","InternLM 2"],["devstral","Devstral"],["granite3.1-dense","Granite 3.1 Dense"],["phi4","Phi 4"],["muse-glimmer","Muse Glimmer"]];
const state = {
  models: familySeed.map(([id,name])=>({id,name,officialUrl:`https://ollama.com/library/${id}`,artifactVerified:false})),
  activeId: familySeed[0][0], filter:'all', compare:[], hostReady:false,
  activeJob:null, hardware:null, capabilities:{}, diagnostics:[], events:[], pending:new Map()
};
const unknown = 'Н/Д';
const numeric = x => typeof x === 'number' && Number.isFinite(x) && x >= 0 ? x : null;
const bytes = x => {const n=numeric(x);if(n===null)return unknown;
  if(n===0)return '0 Б';const units=['Б','КБ','МБ','ГБ','ТБ'];const i=Math.min(4,Math.floor(Math.log(n)/Math.log(1024)));
  return `${(n/Math.pow(1024,i)).toLocaleString('ru-RU',{maximumFractionDigits:i?1:0})} ${units[i]}`;};
const fmtRam = n => numeric(n) === null ? unknown : `${n.toLocaleString('ru-RU',{maximumFractionDigits:1})} ГБ`;
const safeText = x => typeof x === 'string' && x.length>0 ? x : unknown;
const ellipsis = (s,n=180) => String(s ?? '').slice(0,n);
const isDigest = s => typeof s==='string' && /^[a-f0-9]{64}$/i.test(s);
const isOfficial = str => {try {const u=new URL(str);return u.protocol==='https:' && (u.hostname==='ollama.com'||u.hostname==='www.ollama.com') && !u.username && !u.password;}catch{return false;}};
const modelId = x=>typeof x==='string' && /^[a-z0-9][a-z0-9._-]{0,79}$/i.test(x);
function el(tag, className, text){const n=document.createElement(tag);if(className)n.className=className;if(text!==undefined)n.textContent=String(text);return n;}
const current = () => state.models.find(m=>m.id===state.activeId)||state.models[0]||null;
const hasEvidence = m => !!(m && m.artifactVerified===true && m.exactTag && m.immutableRevision && m.license &&
  m.licenseEvidenceUrl && numeric(m.artifactBytes)>0 && isDigest(m.sha256) && isDigest(m.manifestSha256) &&
  (numeric(m.requiredVramGiB)>0 || numeric(m.recommendedRamGiB)>0) && m.compatibilityReviewed===true);
const currentJob = () => state.activeJob && current() &&
  (state.activeJob.modelId===current().id || state.activeJob.modelTag===current().exactTag ||
   state.activeJob.modelTag===current().id) ? state.activeJob : null;
function lineItem(k,v){const dt=el('dt','',k),dd=el('dd','',v);return [dt,dd];}

/* One real action path for all 20 cards: the existing host pull route.
   No downloads are made by the WebView. Family cards stay disabled until
   host supplies approved immutable metadata and download capability. */
const quick20Ids = ["qwen3","qwen3-coder","qwen2.5","qwen2.5-coder","llama3.1","llama3.2","deepseek-r1","gemma3","mistral","phi4","tinyllama","gpt-oss","qwen3-vl","llava","gemma2","mxbai-embed-large","devstral","granite3.1-dense","mistral-nemo","phi3"];

function renderWeightLeads(){
 const root=$('externalLeadsGrid');if(!root)return;root.replaceChildren();
 const leads=Array.isArray(state.externalLeads)?state.externalLeads:[];
 for(const lead of leads.filter(x=>x&&typeof x.id==='string'&&typeof x.displayName==='string'&&
    ['ASR','TTS','IMAGE','VIDEO','TRAINING','ALIGNER'].includes(x.role)).slice(0,40)){
   const item=el('div','lead-card');item.append(el('strong','',lead.displayName),el('small','',lead.role+' · REVIEW_REQUIRED'));
   item.append(el('span','lead-hold','Ожидает SHA / лицензии / адаптера общего host'));
   root.append(item);
 }
 $('externalLeadsStatus').textContent=leads.length?leads.length+' источников · установка недоступна без проверки':'Ожидание проверенного списка от host';
}

function renderQuick20(){
 const grid=$('quickInstallGrid');if(!grid)return;grid.replaceChildren();
 for(const id of quick20Ids){
   const m=state.models.find(x=>x.id===id);if(!m)continue;
   const can=state.hostReady&&state.capabilities?.pull===true&&hasEvidence(m)&&m.id===state.activeId&&$('licenseAck').checked&&!state.pending.has('pull');
   const wrapper=el('div','quick-card');
   const meta=el('span','quick-name',m.name);
   const detail=el('small','quick-sub',can?'Готово к запросу в host':'REVIEW_REQUIRED');
   const btn=el('button','quick-button',can?'↓ Скачать в NOX':m.id===state.activeId?'Нужна проверка':'Выбрать модель');
   btn.type='button';btn.disabled=m.id===state.activeId&&!can;btn.setAttribute('aria-label',can?'Скачать '+m.name+' внутри NOX':'Выбрать '+m.name+' для проверки');
   btn.addEventListener('click',()=>{
     if(!can){state.activeId=m.id;$('licenseAck').checked=false;render();return;}
     sendAction('pull');render();
   });
   wrapper.append(meta,detail,btn);grid.append(wrapper);
 }
 $('quick20Status').textContent=String(grid.children.length)+' моделей · скачивание только через единый host после проверки';
}

function renderCatalog(){const list=$('catalog');list.replaceChildren();const q=$('search').value.toLowerCase().trim();
  const filtered=state.models.filter(m=>(!q||`${m.name} ${m.id}`.toLowerCase().includes(q)) &&
    (state.filter==='all'||state.filter==='verified'&&hasEvidence(m)||state.filter==='compare'&&state.compare.includes(m.id)));
  $('modelCount').textContent=String(filtered.length);
  if(!filtered.length){list.append(el('p','empty-search','Нет совпадений'));return;}
  for(const m of filtered){const b=el('button','model-card'+(m.id===state.activeId?' selected':''));b.type='button';b.setAttribute('aria-current',m.id===state.activeId?'true':'false');
    const mark=el('span','model-mark','✧'),meta=el('span','model-data');meta.append(el('span','model-name',m.name),el('span','model-state',hasEvidence(m)?'ARTIFACT VERIFIED':'REVIEW_REQUIRED'));
    b.append(mark,meta); b.addEventListener('click',()=>{state.activeId=m.id;$('licenseAck').checked=false;render();});
    const check=el('input','compare-check');check.type='checkbox';check.checked=state.compare.includes(m.id);check.setAttribute('aria-label','Сравнить '+m.name);
    check.addEventListener('click',e=>e.stopPropagation());check.addEventListener('change',()=>{const idx=state.compare.indexOf(m.id);if(idx>=0)state.compare.splice(idx,1);else {if(state.compare.length>=2)state.compare.shift();state.compare.push(m.id);}renderCatalog();renderComparison();});
    b.append(check);list.append(b);
  }
}
function renderHero(){const m=current();const j=currentJob();const verified=hasEvidence(m);$('selectedName').textContent=m?.name||'Нет моделей';
  $('heroSubtitle').textContent=m ? `Семейство ${m.id} · ${verified?'Проверенные артефактные данные':'Сведения об артефакте требуют проверки'}`:'Каталог пуст';
  const chips=$('heroChips');chips.replaceChildren();chips.append(el('span','chip '+(verified?'ok':'warning'),verified?'ARTIFACT VERIFIED':'REVIEW_REQUIRED'));
  if(j?.state) chips.append(el('span','chip',j.state));
  const complete=numeric(j?.completedBytes),total=numeric(j?.totalBytes);const realPct=complete!==null&&total!==null&&total>0&&complete<=total?Math.min(100,Math.round(complete/total*100)):null;
  $('orbit').style.setProperty('--pct',realPct===null?'0%':realPct+'%');$('orbit').classList.toggle('working',j?.state==='Running'||j?.state==='Downloading');
  $('orbitLabel').textContent=realPct===null?(j?.state||'НЕТ ЗАГРУЗКИ'):realPct+'% · ПЕРЕДАНО';
  const stateText=j?.state||'Н/Д'; $('jobState').textContent=stateText;$('jobPhase').textContent=j?.status||'Нет активной операции';
  $('transfer').textContent=complete!==null&&total!==null&&total>0?`${bytes(complete)} / ${bytes(total)}`:'Н/Д';
  $('transferNote').textContent=realPct===null?'Без достоверного процента':`Передано ${realPct}% · установка требует receipt`;
  $('modelSize').textContent=verified?bytes(m?.artifactBytes):unknown;
  const cap=state.capabilities||{};const canStop=state.hostReady&&cap.stop===true&&j&&['Queued','Running'].includes(j.state);
  const canRetry=state.hostReady&&cap.retry===true&&j&&['Failed','Cancelled'].includes(j.state);
  $('pullBtn').disabled=!(state.hostReady&&cap.pull===true&&verified&&$('licenseAck').checked&&!state.pending.has('pull'));
  $('importBtn').disabled=!(state.hostReady&&cap.importGguf===true&&$('licenseAck').checked&&!state.pending.has('importGguf'));
  $('stopBtn').disabled=!(canStop&&!state.pending.has('stop'));
  $('retryBtn').disabled=!(canRetry&&!state.pending.has('retry'));
  $('diagBtn').disabled=!(state.hostReady&&cap.diagnose===true&&!state.pending.has('diagnose'));
  $('actionHint').textContent=state.hostReady?'Действия выполняются только после подтверждения Windows host.':'Без host доступен просмотр каталога; операции отключены.';
}
function renderDna(){const m=current();const dl=$('dnaList');dl.replaceChildren();if(!m)return;
  const verified=hasEvidence(m);
  const fields=[['Источник',isOfficial(m.officialUrl)?'Ollama (официальный)':'Неизвестно'],['Тег',verified?safeText(m.exactTag):'REVIEW_REQUIRED'],
    ['Revision',verified?safeText(m.immutableRevision):'REVIEW_REQUIRED'],['Лицензия',verified?safeText(m.license):'REVIEW_REQUIRED'],['Размер',verified?bytes(m.artifactBytes):unknown],
    ['SHA-256 файла',verified&&isDigest(m.sha256)?m.sha256:'REVIEW_REQUIRED'],['SHA-256 манифеста',verified&&isDigest(m.manifestSha256)?m.manifestSha256:'REVIEW_REQUIRED'],['VRAM',verified?fmtRam(m.requiredVramGiB):unknown]];
  for(const [a,b] of fields)dl.append(...lineItem(a,b));const link=$('sourceLink');if(isOfficial(m.officialUrl)){link.href=m.officialUrl;link.removeAttribute('aria-disabled');}else{link.removeAttribute('href');link.setAttribute('aria-disabled','true');}
}
function checkState(label,passed){const item=el('div','check '+(passed===true?'pass':passed===false?'fail':''));item.append(el('strong','',passed===true?'✓':passed===false?'×':'?'),el('span','',label));return item;}
function hardwareCompatibility(m){if(!hasEvidence(m)||!state.hardware)return null;const h=state.hardware;
  const requested=numeric(m.requiredVramGiB),available=numeric(h.vramFreeGiB);if(requested===null||available===null)return null;return available>=requested;
}
function renderPreflight(){const m=current(),h=state.hardware,verified=hasEvidence(m);
 const points=[['Официальный источник',isOfficial(m?.officialUrl)],['Лицензия и права',verified&&!!(m?.license&&m.licenseEvidenceUrl)||null],
  ['Неизменяемая ревизия',verified&&!!m?.immutableRevision||null],['SHA-256 артефакта',verified&&isDigest(m?.sha256)||null],
  ['Размер и место на диске',verified&&numeric(m?.requiredDiskGiB)!==null&&numeric(h?.diskFreeGiB)!==null?h.diskFreeGiB>=m.requiredDiskGiB:null],
  ['Видеопамять ПК',hardwareCompatibility(m)]];
  const container=$('preflightList');container.replaceChildren(...points.map(([label,result])=>checkState(label,result)));
  $('hardwareState').textContent=hardwareCompatibility(m)===true?'Подходит':hardwareCompatibility(m)===false?'Недостаточно':'Неизвестна';
  $('hardwareHint').textContent=h?`VRAM доступно: ${fmtRam(h.vramFreeGiB)}; RAM: ${fmtRam(h.ramFreeGiB)}`:'Нет показаний ПК';
  $('readySummary').textContent=verified&&points.every(([_,ok])=>ok===true)?'Проверки пройдены по полученным данным. Host всё равно подтверждает установку.':'Установка заблокирована до подтверждения всех обязательных данных.';
}
function renderComparison(){const root=$('comparison');root.replaceChildren();if(state.compare.length!==2){root.textContent='Выберите ровно две модели галочками в каталоге.';return;}
 const grid=el('div','compare-grid');for(const id of state.compare){const m=state.models.find(x=>x.id===id);if(!m)continue;const col=el('div','compare-col');col.append(el('h4','',m.name));const dl=el('dl');
  for(const [label,value] of [['Статус',hasEvidence(m)?'VERIFIED':'REVIEW_REQUIRED'],['Размер',hasEvidence(m)?bytes(m.artifactBytes):unknown],['VRAM',hasEvidence(m)?fmtRam(m.requiredVramGiB):unknown],['Лицензия',hasEvidence(m)?safeText(m.license):'REVIEW_REQUIRED'],['Тег',hasEvidence(m)?safeText(m.exactTag):'REVIEW_REQUIRED']])dl.append(...lineItem(label,value));col.append(dl);grid.append(col);}root.append(grid);
}
function renderEvents(){const feed=$('eventFeed');feed.replaceChildren();if(state.events.length===0){feed.append(el('li','empty','Нет событий от host.'));return;}
 for(const evt of state.events.slice(0,10)){const li=el('li');const date=new Date(evt.atUtc||evt.AtUtc||'');const time=isNaN(date.getTime())?'--:--':date.toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
  li.append(el('span','event-time',time),el('span','',ellipsis(`${evt.modelTag||evt.ModelTag||'MODEL'} · ${evt.phase||evt.Phase||'event'} · ${evt.status||evt.Status||''}`,150)));feed.append(li);}
}
function render(){renderCatalog();renderHero();renderDna();renderPreflight();renderComparison();renderEvents();renderQuick20();renderWeightLeads();}
function sendAction(action){const c=state.capabilities||{};const job=currentJob();if(!state.hostReady||c[action]!==true)return;
 if(action==='pull'&&(!hasEvidence(current())||!$('licenseAck').checked))return;
 if(action==='importGguf'&&!$('licenseAck').checked)return;
 if(['stop','retry'].includes(action)&&(!job||!job.jobId))return;
 if(action==='stop'&&!['Queued','Running'].includes(job.state))return;
 if(action==='retry'&&!['Failed','Cancelled'].includes(job.state))return;
 if(!['diagnose','pull','importGguf','stop','retry'].includes(action))return;
 if(state.pending.has(action))return;const commandId='c'+Date.now().toString(36)+Math.random().toString(36).slice(2,9);
 const data={type:'p03.command.v1',commandId,action,modelId:current()?.id||null,
  licenseAcknowledged:['pull','importGguf'].includes(action)&&$('licenseAck').checked,
  jobId:['stop','retry'].includes(action)?job.jobId:null};
 const m=current(),pending={commandId,id:m?.id||null,tag:m?.exactTag||null,revision:m?.immutableRevision||null,manifest:m?.manifestSha256||null,timer:null};
 state.pending.set(action,pending);renderHero();renderQuick20();
 try{window.chrome.webview.postMessage(data);
  pending.timer=setTimeout(()=>{if(state.pending.get(action)!==pending)return;state.pending.delete(action);renderHero();renderQuick20();showToast('Нет ACK host: исход неизвестен; проверьте очередь.');},45000);
  showToast('Команда отправлена host. Ожидание ответа.');
 }catch{if(pending.timer!==null)clearTimeout(pending.timer);state.pending.delete(action);renderHero();renderQuick20();showToast('Связь с host отсутствует.');}
 // Pending is not interpreted as success; delayed ACK clears this lock.
}
let toastTimer;function showToast(msg){const n=$('toast');n.textContent=ellipsis(msg,240);n.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>n.hidden=true,4500);}
function processMessage(data){if(!data||typeof data!=='object'||!['p03.snapshot.v1','p03.event.v1','p03.command.ack.v1'].includes(data.type))return;
 if(data.type==='p03.snapshot.v1'){
  if(!Array.isArray(data.models)||!data.models.length||data.models.length>250)return;
  const models=data.models;
  if(models.some(m=>!m||!modelId(m.id)||typeof m.name!=='string'||m.name.length>100)||
    new Set(models.map(m=>m.id)).size!==models.length)return;
  const before=current(),after=models.find(m=>m.id===state.activeId);
  if(!before||!after||['exactTag','immutableRevision','sha256','manifestSha256','license','artifactVerified'].some(k=>before[k]!==after[k]))$('licenseAck').checked=false;
  state.models=models.map(m=>({...m}));
  if(!state.models.some(m=>m.id===state.activeId))state.activeId=state.models[0].id;
  // Preserve terminal and monotone state when an older host snapshot arrives.
  const incoming=data.activeJob,old=state.activeJob;
  const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  if(incoming!=null&&(
      typeof incoming!=='object'||!uuid.test(incoming.jobId||'')||
      typeof incoming.modelTag!=='string'||incoming.modelTag.length>160||
      !['Queued','Running','Cancelling','Completed','Cancelled','Failed'].includes(incoming.state)))return;
  let next=incoming?{...incoming}:null;
  if(next){
    const done=numeric(next.completedBytes),total=numeric(next.totalBytes);
    if(done!==null&&total!==null&&done>total)return;
    next.completedBytes=done;next.totalBytes=total;
    if(old&&old.jobId===next.jobId&&old.modelTag===next.modelTag){
      if(['Completed','Cancelled','Failed'].includes(old.state)&&next.state!==old.state)next={...old};
      else{
        if(old.state==='Cancelling'&&['Queued','Running'].includes(next.state))next.state='Cancelling';
        if(['Running','Cancelling'].includes(old.state)&&next.state==='Queued')next.state=old.state;
        if(numeric(old.completedBytes)!==null&&
           (next.completedBytes===null||next.completedBytes<old.completedBytes)){
          next.completedBytes=old.completedBytes;next.totalBytes=old.totalBytes;
        }
        if(numeric(old.totalBytes)!==null&&
           (next.totalBytes===null||next.totalBytes<old.totalBytes))next.totalBytes=old.totalBytes;
        if(next.completedBytes!==null&&next.totalBytes!==null&&next.completedBytes>next.totalBytes)return;
      }
    }
  }
  state.hostReady=true;state.activeJob=next;
  state.hardware=data.hardware&&typeof data.hardware==='object'?data.hardware:null;
  state.capabilities=data.capabilities&&typeof data.capabilities==='object'?data.capabilities:{};
  state.diagnostics=Array.isArray(data.diagnostics)?data.diagnostics.slice(0,30):[];
  state.externalLeads=Array.isArray(data.externalLeads)?data.externalLeads.filter(x=>x.downloadAllowed===false&&x.status==='REVIEW_REQUIRED').slice(0,40):[];
  $('hostStatus').textContent='Синхронизировано с Windows host';$('hostLight').classList.add('online');$('eventSignal').textContent='● LIVE';$('eventSignal').classList.add('live');render();
 }else if(data.type==='p03.event.v1'){
  const evt=data.event;
  if(!evt||typeof evt!=='object'||typeof evt.jobId!=='string'||typeof evt.phase!=='string')return;
  if(!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(evt.jobId)||
    !['started','progress','completed','failed','cancelled'].includes(evt.phase)||
    (evt.modelTag!==undefined&&(typeof evt.modelTag!=='string'||evt.modelTag.length>160))||
    (evt.status!==undefined&&(typeof evt.status!=='string'||evt.status.length>512)))return;
  const safe={...evt,status:typeof evt.status==='string'?evt.status:'',modelTag:typeof evt.modelTag==='string'?evt.modelTag:''};
  state.events.unshift(safe);state.events.length=Math.min(state.events.length,40);
  // Queue ownership is independent of the card currently being inspected.
  // Preserve background completion/STOP so returning to its card is truthful.
  const job=state.activeJob;
  if(job&&evt.jobId===job.jobId&&(!evt.modelTag||evt.modelTag===job.modelTag)&&
     !['Completed','Failed','Cancelled'].includes(job.state)){
    if(typeof evt.status==='string')job.status=evt.status;
    const done=numeric(evt.completedBytes),total=numeric(evt.totalBytes);
    if(done!==null&&total!==null&&total>0&&done<=total&&
       (numeric(job.completedBytes)===null||done>=job.completedBytes)&&
       (numeric(job.totalBytes)===null||total>=job.totalBytes)){
      job.completedBytes=done;job.totalBytes=total;
    }
    const terminal={completed:'Completed',failed:'Failed',cancelled:'Cancelled'}[evt.phase];
    if(terminal)job.state=terminal;
  }
  render();
 }else if(data.type==='p03.command.ack.v1'){
  if(!['pull','importGguf','stop','retry','diagnose'].includes(data.action)||typeof data.commandId!=='string'||typeof data.accepted!=='boolean')return;
  const pending=state.pending.get(data.action);if(!pending||pending.commandId!==data.commandId)return;
  if(pending.timer!==null)clearTimeout(pending.timer);
  state.pending.delete(data.action);renderHero();renderQuick20();
  const m=current(),samePin=pending.id===(m?.id||null)&&pending.tag===(m?.exactTag||null)&&pending.revision===(m?.immutableRevision||null)&&pending.manifest===(m?.manifestSha256||null);
  showToast(!samePin?'ACK от ранее выбранной модели; проверьте очередь.':data.accepted===true?'Host принял команду; установка требует receipt.':`Host отклонил: ${ellipsis(data.reason||'причина не указана')}`);
 }}
$('search').addEventListener('input',renderCatalog);
for(const b of document.querySelectorAll('[data-filter]'))b.addEventListener('click',()=>{state.filter=b.dataset.filter;for(const btn of document.querySelectorAll('[data-filter]')){btn.classList.toggle('active',btn===b);btn.setAttribute('aria-pressed',String(btn===b));}renderCatalog();});
$('pullBtn').addEventListener('click',()=>sendAction('pull'));
$('importBtn').addEventListener('click',()=>sendAction('importGguf'));
$('licenseAck').addEventListener('change',()=>{renderHero();renderQuick20();});
$('stopBtn').addEventListener('click',()=>sendAction('stop'));
$('retryBtn').addEventListener('click',()=>sendAction('retry'));
$('diagBtn').addEventListener('click',()=>sendAction('diagnose'));
document.addEventListener('keydown',e=>{if(e.key==='/'&&!['INPUT','TEXTAREA'].includes(document.activeElement?.tagName)){e.preventDefault();$('search').focus();}});
if(window.chrome?.webview?.addEventListener)window.chrome.webview.addEventListener('message',e=>processMessage(e.data));
render();