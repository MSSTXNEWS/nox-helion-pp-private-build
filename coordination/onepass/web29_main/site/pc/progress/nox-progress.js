/* NOX Evolution: separate page in the existing final WEB. No model call,
   execution endpoint, autonomous browser mutation, fabricated metric or CDN. */
(function(root){'use strict';
const NOX_EVOLUTION_ASSET_BASE=typeof document==='undefined'?null:new URL('.',document.currentScript?.src||location.href);
const KINDS=['self_improvement','knowledge','weights'];
const LABEL={self_improvement:'Самоулучшение',knowledge:'Обучение знаний',weights:'Обучение весов'};
const UNIT={self_improvement:'внедрений с проверкой',knowledge:'новых записей S03',weights:'шагов оптимизатора'};
const STATUS={verified:'PASS · ПОДТВЕРЖДЕНО',active:'HOLD · В РАБОТЕ',blocked:'HOLD · ОЖИДАНИЕ',failed:'FAIL · ОШИБКА',source:'SOURCE · ИСХОДНИКИ',unknown:'HOLD · НЕ ПРОВЕРЕНО'};
const finite=v=>typeof v==='number'&&Number.isFinite(v)&&v>=0;
const SHA=/^[a-f0-9]{64}$/;const ID=/^[A-Za-z0-9._:-]{1,160}$/;
const color=s=>s==='verified'?'green':s==='failed'?'red':'yellow';
/* A missing persisted S03 hour must appear as HOLD, not disappear. */
function eligibleHourCards(data){
 if(!data||!Array.isArray(data.hours))return [];
 if(data.mode==='source_snapshot')return data.hours.filter(h=>h.closed===true);
 const at=Date.parse(data.generated_at);
 return Number.isFinite(at)?data.hours.filter(h=>Number.isFinite(Date.parse(h.end))&&Date.parse(h.end)<=at):[];
}
/* Old API snapshots cannot assert CURRENT GPU speed or health. */
function nativeFresh(raw,now=Date.now()){
 const at=Date.parse(raw?.generated_at),age=now-at;
 return raw?.mode==='native'&&Number.isFinite(at)&&age>=-30000&&age<=120000;
}
/* Aggregate counts need fresh owner-native proof, not merely a native label. */
/* Reconcile the native aggregate with independently checked event proofs.
   A fresh API timestamp alone cannot turn a contradictory sum into progress. */
function nativeGroupValue(data,kind){
 const g=data?.groups?.[kind];
 if(!data?.liveFresh||!g||data.truncated===true||
    !Number.isSafeInteger(g.value)||g.value<0||!Array.isArray(data.events))return null;
 const verified=data.events.filter(e=>e.kind===kind&&e.state==='verified'&&
    e.evidence==='native'&&proofValid(e));
 let total=0;
 for(const e of verified){
  const delta=kind==='weights'?e.proof.successful_optimizer_updates:
              kind==='knowledge'?e.proof.records_added:1;
  if(!Number.isSafeInteger(delta)||delta<0||!Number.isSafeInteger(total+delta))return null;
  total+=delta;
 }
 // A complete zero is possible only when the original native collector
 // explicitly supplied complete coverage. Partial zero means UNKNOWN.
 if(!verified.length&&g.complete!==true)return null;
 return total===g.value?total:null;
}
/* Lose current hardware/latency claims immediately on failed refresh. */
function expireNative(data){
 if(!data||data.mode!=='native')return data;
 // A disconnected native snapshot cannot keep advertising a task as RUNNING.
 // Keep signed historical PASS events intact; only in-flight visual state expires.
 return {...data,liveFresh:false,
   events:(data.events||[]).map(e=>e.state==='active'?{...e,state:'unknown'}:e),
   metrics:Object.fromEntries(Object.keys(data.metrics||{}).map(k=>[k,null]))};
}
const safeURL=(s,origin='https://local.invalid')=>{try{if(typeof s!=='string'||s.length>700||s.startsWith('//'))return null;const u=new URL(s,origin);return ((u.protocol==='https:'&&!u.username&&!u.password)||(s.startsWith('/')&&u.origin===origin))?u.href:null;}catch{return null;}};
function proofValid(e){const p=e.proof||{};if(!SHA.test(p.receipt_sha256||''))return false;
 if(e.kind==='weights')return Number.isSafeInteger(p.step_before)&&p.step_before>=0&&Number.isSafeInteger(p.step_after)&&p.step_after>p.step_before&&Number.isSafeInteger(p.successful_optimizer_updates)&&p.successful_optimizer_updates>0&&p.successful_optimizer_updates<=p.step_after-p.step_before&&SHA.test(p.tensor_before||'')&&SHA.test(p.tensor_after||'')&&p.tensor_before!==p.tensor_after&&SHA.test(p.checkpoint_sha256||'')&&(p.skipped_optimizer_updates===undefined||(Number.isSafeInteger(p.skipped_optimizer_updates)&&p.skipped_optimizer_updates>=0&&p.successful_optimizer_updates+p.skipped_optimizer_updates<=p.step_after-p.step_before));
 if(e.kind==='knowledge')return Number.isSafeInteger(p.records_added)&&p.records_added>=0&&SHA.test(p.s03_readback_sha256||'');
 return p.independent_test_passed===true&&/^[a-f0-9]{40,64}$/.test(p.deployed_sha||'');}
function normalize(raw){if(!raw||raw.schema!=='NOX_EVOLUTION_V1'||!['native','source_snapshot'].includes(raw.mode)||!Array.isArray(raw.events)||raw.events.length>5000)throw Error('HOLD_PROGRESS_SCHEMA');
 const liveFresh=nativeFresh(raw);
 const seen=new Set();const events=[];
 for(const r of raw.events){if(!r||!ID.test(r.id||'')||seen.has(r.id)||!KINDS.includes(r.kind)||!STATUS[r.state]||!Number.isFinite(Date.parse(r.at)))continue;seen.add(r.id);
  const e={...r,title:String(r.title||'Событие').slice(0,120),summary:String(r.summary||'').slice(0,500),detail:String(r.detail||'').slice(0,6000),tags:Array.isArray(r.tags)?r.tags.filter(t=>typeof t==='string'&&t.length<=40).slice(0,12):[],sources:Array.isArray(r.sources)?r.sources.filter(s=>s&&typeof s.label==='string'&&safeURL(s.url)).slice(0,8):[]};
  if(e.state==='verified'&&(raw.mode!=='native'||e.evidence!=='native'||!proofValid(e)))e.state=e.evidence==='source'?'source':'unknown';
  if(raw.mode==='native'&&!liveFresh&&e.state==='active')e.state='unknown';
  events.push(e);
 }
 events.sort((a,b)=>Date.parse(b.at)-Date.parse(a.at)||a.id.localeCompare(b.id));
 const metrics={};for(const k of ['ttft_ms','tokens_per_second','gpu0_percent','gpu1_percent','ram_percent']){const v=raw.metrics?.[k];metrics[k]=liveFresh&&finite(v)&&(!k.includes('percent')||v<=100)?v:null;}
 const hours=Array.isArray(raw.hours)?raw.hours.filter(h=>h&&ID.test(h.id||'')&&Number.isFinite(Date.parse(h.start))&&Number.isFinite(Date.parse(h.end))).slice(0,168).map(h=>({...h,closed:h.closed===true&&(raw.mode==='source_snapshot'||(h.readback_verified===true&&SHA.test(h.readback_sha256||'')&&h.readback_state==='S03_PERSISTED_HOUR_READBACK'))})):[];
 const hourly=raw.hourly_readback||{};
 const readback=raw.mode==='native'&&Number.isSafeInteger(hourly.expected_closed)&&Number.isSafeInteger(hourly.persisted_verified)&&hourly.expected_closed>=hourly.persisted_verified&&hourly.persisted_verified>=0?`${hourly.persisted_verified}/${hourly.expected_closed}`:'HOLD';
 return {...raw,events,metrics,hours,liveFresh,hourlyReadback:readback,groups:raw.groups&&typeof raw.groups==='object'?raw.groups:{}};
}
function filterEvents(events,{status='all',tag=null,search=''}={}){const q=search.trim().toLocaleLowerCase('ru');return events.filter(e=>(status==='all'||color(e.state)===status)&&(!tag||e.tags.includes(tag))&&(!q||[e.title,e.summary,e.detail,...e.tags].join(' ').toLocaleLowerCase('ru').includes(q)));}
root.NoxEvolution={normalize,filterEvents,safeURL,color,proofValid,eligibleHourCards,nativeFresh,nativeGroupValue,expireNative};
if(typeof document==='undefined')return;
const $=id=>document.getElementById(id);const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
const format=(date,opts={})=>new Intl.DateTimeFormat('ru-RU',{timeZone:'Europe/Moscow',hour:'2-digit',minute:'2-digit',...opts}).format(new Date(date));
const fulltime=date=>format(date,{day:'2-digit',month:'2-digit',year:'numeric'});
const state={data:null,status:'all',tag:null,search:'',more:false,loading:false,lastFocus:null};
const dot=s=>node('i',undefined,'dot '+color(s));
function graph(kind){const ns='http://www.w3.org/2000/svg';const svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 320 48');svg.setAttribute('class','metric-chart');svg.setAttribute('role','img');svg.setAttribute('aria-label','Количество наблюдаемых событий по часам, не процент интеллекта');
 for(const y of [12,28,44]){const p=document.createElementNS(ns,'path');p.setAttribute('d',`M0 ${y} H320`);p.setAttribute('class','chart-grid');svg.append(p);}
 const bins=(state.data.hours||[]).slice(0,24).reverse().map(h=>state.data.events.filter(e=>e.kind===kind&&Date.parse(e.at)>=Date.parse(h.start)&&Date.parse(e.at)<Date.parse(h.end)).length);
 if(!bins.some(v=>v>0)){const t=document.createElementNS(ns,'text');t.setAttribute('x','0');t.setAttribute('y','31');t.setAttribute('fill','#8e8f92');t.setAttribute('font-size','9');t.textContent='Нет подтверждённого временного ряда';svg.append(t);return svg;}
 const max=Math.max(...bins,1);const pts=bins.map((v,i)=>`${i*320/Math.max(1,bins.length-1)},${42-v/max*34}`);const path=document.createElementNS(ns,'path');path.setAttribute('d','M'+pts.join(' L'));path.setAttribute('class','chart-trace');svg.append(path);const fill=path.cloneNode();fill.setAttribute('class','chart-fill');fill.setAttribute('d','M0,48 L'+pts.join(' L')+' L320,48 Z');svg.prepend(fill);return svg;}
function renderMetrics(){const box=$('metrics');box.replaceChildren();for(const [i,k] of KINDS.entries()){
 const g=state.data.groups[k]||{};const rows=state.data.events.filter(e=>e.kind===k);const verifiedValue=nativeGroupValue(state.data,k);
 const a=node('article',undefined,'metric-card');a.dataset.kind=k;const top=node('div',undefined,'metric-top');top.append(node('h2',LABEL[k]),node('span','0'+(i+1),'metric-index'));const val=node('div',undefined,'metric-main');val.append(node('strong',verifiedValue===null?'—':(g.complete===true?'':'≥ ')+verifiedValue.toLocaleString('ru-RU'),'metric-value'),node('span',UNIT[k],'metric-unit'));
 const sourceCount=rows.filter(e=>e.evidence==='source').length;const sub=node('p',sourceCount?`${sourceCount} событий в исходниках · внедрение отдельно`:verifiedValue===null?'Нативные квитанции ещё не получены':g.complete===true?'Полный учёт за выбранное окно':'Подтверждённая часть; полнота учёта не доказана','metric-sub');const baseline=node('div',undefined,'metric-baseline');baseline.append(node('span','СОБЫТИЯ / 24 ЧАСА'),node('span',state.data.liveFresh?'S03 · '+state.data.hourlyReadback:state.data.mode==='native'?'S03 · УСТАРЕЛО':'SOURCE ONLY','metric-scope'));a.append(top,val,sub,graph(k),baseline);box.append(a);}
 const rt=$('runtime');rt.replaceChildren();const labels={ttft_ms:['Первый токен',' мс'],tokens_per_second:['Генерация',' ток/с'],gpu0_percent:['GPU 0 · чат','%'],gpu1_percent:['GPU 1 · обучение','%'],ram_percent:['Оперативная память','%']};for(const [k,[label,unit]]of Object.entries(labels)){const a=node('div',undefined,'runtime-item');a.append(node('span',label),node('b',state.data.metrics[k]===null?'—':state.data.metrics[k].toLocaleString('ru-RU',{maximumFractionDigits:1})+unit));rt.append(a);}}
function hourSummary(h,k){if(state.data.mode==='native'&&!h.closed)return `${LABEL[k]}: HOLD · нет подтверждённой почасовой записи S03`;const g=h.groups?.[k];if(!g)return `${LABEL[k]}: нет данных`;const sourceCount=state.data.events.filter(e=>e.kind===k&&e.evidence==='source'&&Date.parse(e.at)>=Date.parse(h.start)&&Date.parse(e.at)<Date.parse(h.end)).length;
 if(sourceCount&&state.data.mode!=='native')return `${LABEL[k]}: ${sourceCount} событий в исходниках`;
 if(state.data.mode!=='native')return `${LABEL[k]}: нативные данные не получены`;
 return typeof g.summary==='string'?g.summary.slice(0,250):`${LABEL[k]}: нет данных`;}
function renderHours(){const box=$('hourlyCards');box.replaceChildren();let hours=eligibleHourCards(state.data);
 if(state.data.mode==='source_snapshot'){const withEvents=hours.filter(h=>state.data.events.some(e=>Date.parse(e.at)>=Date.parse(h.start)&&Date.parse(e.at)<Date.parse(h.end)));if(withEvents.length)hours=withEvents;}
 const displayed=state.more?hours:hours.slice(0,3);$('moreHours').hidden=hours.length<=3;$('moreHours').textContent=state.more?'Свернуть':'Показать ещё';
 if(!displayed.length){box.append(node('p',state.data.mode==='native'?'HOLD · Нет сохранённых и проверенных почасовых квитанций S03; агрегированный снимок не считается журналом.':'За завершённые часы пока нет отчётов исходников.','evo-empty'));return;}
 for(const h of displayed){const b=node('button',undefined,'hour-card');b.type='button';b.dataset.hourId=h.id;const top=node('div',undefined,'hour-top');top.append(node('b',format(h.start)+' — '+format(h.end)),node('small',format(h.start,{day:'2-digit',month:'2-digit'}).split(',')[0]+' · МСК'),node('span',state.data.mode==='native'?(h.closed?'S03 · SHA OK':'HOLD · НЕТ КВИТАНЦИИ S03'):'SOURCE · НЕ LIVE','hour-state'));b.append(top);
 for(const k of KINDS){const row=node('span',undefined,'hour-row');row.append(dot(state.data.mode==='native'&&h.closed?h.groups?.[k]?.state:'blocked'),node('span',hourSummary(h,k)));b.append(row);}b.append(node('span','Открыть итог часа ↗','hour-open'));b.addEventListener('click',()=>openHour(h.id));box.append(b);}}
function tagButton(tag,cls){const b=node('button','#'+tag,cls);b.type='button';b.dataset.tag=tag;b.addEventListener('click',()=>{state.tag=state.tag===tag?null:tag;renderTags();renderEvents();});return b;}
function renderTags(){const box=$('tagFilters');box.replaceChildren();const all=node('button','Все теги');all.type='button';all.setAttribute('aria-pressed',String(!state.tag));all.onclick=()=>{state.tag=null;renderTags();renderEvents();};box.append(all);const tags=[...new Set(state.data.events.flatMap(e=>e.tags))].sort((a,b)=>a.localeCompare(b,'ru')).slice(0,48);for(const t of tags){const b=tagButton(t);b.setAttribute('aria-pressed',String(state.tag===t));box.append(b);}}
function renderEvents(){const shown=filterEvents(state.data.events,state);$('eventCount').textContent=`${shown.length} / ${state.data.events.length} событий${state.data.truncated===true?' · выборка неполная':''}`;$('filterHint').textContent=state.tag?`Тег #${state.tag} · выбранные фильтры применяются ко всем трём потокам.`:'Цвет показывает статус. Отметка «ИСХОДНИКИ» не означает установку на сервер.';
 const box=$('columns');box.replaceChildren();for(const k of KINDS){const lane=node('section',undefined,'evo-lane');lane.dataset.kind=k;const rows=shown.filter(e=>e.kind===k);const header=node('div',undefined,'lane-heading');header.append(node('h3',LABEL[k]),node('span',String(rows.length),'lane-count'));lane.append(header);
 for(const e of rows){const a=node('article',undefined,'event-card');a.dataset.eventId=e.id;a.dataset.state=e.state;a.style.setProperty('--event-color',`var(--${color(e.state)})`);const meta=node('div',undefined,'event-meta');const status=node('span',STATUS[e.state],'event-state');status.prepend(dot(e.state));meta.append(status,node('time',format(e.at)));const title=node('button',e.title,'event-title');title.type='button';title.onclick=()=>openEvent(e.id);const summary=node('p',e.summary,'event-summary');const tags=node('div',undefined,'event-tags');e.tags.forEach(t=>tags.append(tagButton(t)));const link=node('button','Подробности и источник ↗','event-open');link.type='button';link.onclick=()=>openEvent(e.id);a.append(meta,title,summary,tags,link);lane.append(a);}
 if(!rows.length){const blank=node('div',undefined,'evo-empty');blank.append(node('b',state.tag||state.search||state.status!=='all'?'Нет совпадений':'Нет подтверждённых событий'),node('span',k==='weights'?'Шаги, изменение тензоров и checkpoint появятся после квитанции тренера.':k==='knowledge'?'Новые знания учитываются после сохранения и обратного чтения S03.':'Здесь будут исправления, проверки и фактические внедрения.'));lane.append(blank);}box.append(lane);}}
function showDialog(hash){state.lastFocus=document.activeElement;const dialog=$('eventDialog');if(!dialog.open)dialog.showModal();if(location.hash!==hash)history.replaceState(null,'',location.href.split('#')[0]+hash);}
function addSources(body,e){if(!e.sources?.length)return;const links=node('div',undefined,'detail-sources');for(const s of e.sources){const url=safeURL(s.url,location.origin);if(!url)continue;const a=node('a',s.label+' ↗');a.href=url;a.target='_blank';a.rel='noopener noreferrer';links.append(a);}body.append(links);}
function openEvent(id){const e=state.data.events.find(x=>x.id===id);if(!e)return;const b=$('detailBody');b.replaceChildren();$('detailKind').textContent=LABEL[e.kind]+' / '+STATUS[e.state];const h=node('h2',e.title);h.id='detailTitle';b.append(h,node('p',fulltime(e.at)+' · МСК · '+(e.evidence==='native'?'Нативная квитанция':e.evidence==='source'?'Только исходники / тесты':'Доказательство не получено'),'detail-time'),node('p',e.summary),node('p',e.detail));
 const tags=node('div',undefined,'event-tags');e.tags.forEach(t=>tags.append(node('span','#'+t)));b.append(tags);if(e.proof&&Object.keys(e.proof).length){const d=node('details');d.append(node('summary','Контрольные данные и SHA'),node('pre',JSON.stringify(e.proof,null,2)));b.append(d);}addSources(b,e);const a=node('a','Постоянная ссылка на событие','hour-permalink');a.href='#event='+encodeURIComponent(e.id);b.append(a);showDialog(a.getAttribute('href'));}
function openHour(id){const h=state.data.hours.find(x=>x.id===id);if(!h)return;const body=$('detailBody');body.replaceChildren();$('detailKind').textContent='ПОЧАСОВОЙ ОТЧЁТ / ТРИ ПОТОКА · '+(state.data.mode==='native'?(h.closed?'S03 VERIFIED':'HOLD · S03 READBACK'):'SOURCE ONLY');const title=node('h2',format(h.start)+' — '+format(h.end));title.id='detailTitle';body.append(title,node('p',fulltime(h.start)+' · МСК','detail-time'));
 for(const k of KINDS){const group=node('section',undefined,'detail-group');group.append(node('h3',LABEL[k]),node('p',hourSummary(h,k)));const rows=state.data.events.filter(e=>e.kind===k&&Date.parse(e.at)>=Date.parse(h.start)&&Date.parse(e.at)<Date.parse(h.end));for(const e of rows){const b=node('button',format(e.at)+' · '+e.title+' ↗');b.type='button';b.onclick=()=>openEvent(e.id);group.append(b);}body.append(group);}const a=node('a','Постоянная ссылка на час','hour-permalink');a.href='#hour='+id;body.append(a);showDialog(a.getAttribute('href'));}
function route(){if(!state.data)return;const m=/^#(event|hour)=([A-Za-z0-9._:%-]+)$/.exec(location.hash);if(!m)return;let id;try{id=decodeURIComponent(m[2]);}catch{return;}if(m[1]==='event')openEvent(id);else openHour(id);}
function apply(raw){state.data=normalize(raw);if(state.tag&&!state.data.events.some(e=>e.tags.includes(state.tag)))state.tag=null;renderMetrics();renderHours();renderTags();renderEvents();$('connection').lastChild.textContent=state.data.liveFresh?'Журнал S03':state.data.mode==='native'?'Снимок устарел':'Снимок исходников';$('connection').style.color=state.data.liveFresh?'var(--green)':'var(--yellow)';$('sourceNote').textContent=state.data.truncated===true?'HOLD · Событий больше 5000: показана неполная выборка. Общий прогресс весов, знаний и самоулучшений неизвестен; источник и почасовой readback проверяйте отдельно.':state.data.liveFresh?'Существующая S03 · сохранённые часы с независимым readback: '+state.data.hourlyReadback+'. Положительные результаты отделены от исходников; неполное покрытие отмечено «≥».':state.data.mode==='native'?'HOLD · Данные API устарели либо время снимка недостоверно. Исторические квитанции видимы, но GPU/скорость сейчас неизвестны.':'СНИМОК ИСХОДНИКОВ — не live. Авторизованный журнал OneHost недоступен; ниже только исходные изменения. Знания, веса и ресурсы не предполагаются.';$('updatedAt').textContent='Снимок: '+fulltime(state.data.generated_at)+' МСК';route();}
async function json(url){const ac=new AbortController();const timeout=setTimeout(()=>ac.abort(),7000);try{const r=await fetch(url,{credentials:'same-origin',cache:'no-store',signal:ac.signal,headers:{Accept:'application/json'}});if(!r.ok){const ex=Error('HTTP_'+r.status);ex.status=r.status;throw ex;}const text=await r.text();if(text.length>3000000)throw Error('RESPONSE_TOO_LARGE');return JSON.parse(text);}finally{clearTimeout(timeout);}}
async function refresh(){if(state.loading||document.hidden)return;state.loading=true;$('refresh').disabled=true;try{const embedded=$('nox-source-snapshot');if(embedded){apply(JSON.parse(embedded.textContent));return;}try{apply(await json('/api/nox/evolution?hours=24'));}catch(e){if(e.status===401||e.status===403){const dlg=$('eventDialog');if(dlg?.open)dlg.close();$('detailBody').replaceChildren();$('tagFilters').replaceChildren();$('eventCount').textContent='—';$('filterHint').textContent='';state.data=null;$('metrics').replaceChildren();$('runtime').replaceChildren();$('hourlyCards').replaceChildren();$('columns').replaceChildren();$('sourceNote').textContent='Требуется действующая сессия владельца. Данные журнала не загружаются.';$('connection').lastChild.textContent='Нужен вход';return;}apply(await json(new URL('source-snapshot.json',NOX_EVOLUTION_ASSET_BASE).href));}}catch{if(state.data){state.data=expireNative(state.data);renderMetrics();renderEvents();renderHours();$('connection').style.color='var(--yellow)';$('sourceNote').textContent='СВЯЗЬ ПОТЕРЯНА. Отображён последний снимок; он не считается текущим live-состоянием.';$('connection').lastChild.textContent='Устаревший снимок';}else{$('sourceNote').textContent='Журнал недоступен. Числа не подставляются: проверьте авторизацию и подключение событий OneHost.';$('connection').lastChild.textContent='Нет данных';}}finally{state.loading=false;$('refresh').disabled=false;}}
function init(){if(!$('metrics'))return;$('statusFilters').addEventListener('click',e=>{const b=e.target.closest('button[data-filter]');if(!b)return;state.status=b.dataset.filter;for(const x of $('statusFilters').querySelectorAll('button'))x.setAttribute('aria-pressed',String(x===b));if(state.data)renderEvents();});$('search').addEventListener('input',e=>{state.search=e.target.value;if(state.data)renderEvents();});$('moreHours').onclick=()=>{state.more=!state.more;renderHours();};$('refresh').onclick=()=>void refresh();$('closeDialog').onclick=()=>$('eventDialog').close();$('eventDialog').addEventListener('close',()=>{history.replaceState(null,'',location.href.split('#')[0]);state.lastFocus?.focus?.();});window.addEventListener('hashchange',route);const clock=()=>{$('clock').textContent=format(new Date(),{second:'2-digit'});};clock();const timer=setInterval(()=>{if(!document.hidden)clock();},1000);const poll=setInterval(()=>void refresh(),30000);document.addEventListener('visibilitychange',()=>{document.documentElement.dataset.evoHidden=String(document.hidden);if(!document.hidden){clock();void refresh();}});window.addEventListener('pagehide',e=>{if(!e.persisted){clearInterval(timer);clearInterval(poll);}},{once:true});void refresh();root.NoxEvolution.refresh=refresh;root.NoxEvolution.state=state;root.NoxEvolution.apply=apply;}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})(globalThis);
