/** R11 WOW · NOX EXPRESS INTEGRATOR; secondary visual interface over ONE original WebView2 client.
 * Only the original native client may act. No invented AI, training, hardware metrics, models or progress.
 */
export const R11_WORLD_IDS=Object.freeze(['work','intelligence','knowledge','learning','entertainment','people','creative','business','world','pc']);
export const R11_READ_ACTIONS=Object.freeze([
  {id:'models',label:'Библиотека моделей',route:'models.catalog'},
  {id:'queue',label:'Загрузки и очередь',route:'models.queue'},
  {id:'models-check',label:'Совместимость моделей',route:'models.preflight'},
  {id:'gpu',label:'Диагностика GPU',route:'gpu.preflight'},
  {id:'chat-model',label:'Активная модель',route:'chat.model'},
  {id:'sources',label:'Исходники и интеграции',route:'chat.commands',action:'selfbuilder.sources.inspect'},
  {id:'learning',label:'Обучение · доказательства',route:'chat.commands',action:'selfbuilder.learning.proofs'},
  {id:'tasks',label:'Самодописание · задания',route:'chat.commands',action:'selfbuilder.worker.status'},
  {id:'plan',label:'План самостоятельного обучения',route:'chat.commands',action:'selfbuilder.study.queue'},
  {id:'coding-models',label:'Модели программиста',route:'chat.commands',action:'selfbuilder.coding.models'}
]);
const VERIFIED=new Set(['COMPLETED','STOP_REQUESTED','HOLD']);
const ID=/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const SAFE_COUNT = n=>Number.isSafeInteger(n)&&n>=0&&n<=1000000;
/** UI-only projection; never call this a proof of completion beyond the native response. */
export function projectNativeReply(reply){
  if(!reply||typeof reply!=='object'||!VERIFIED.has(reply.state))return Object.freeze({state:'HOLD',label:'Нет подтверждённого ответа ядра',value:'Н/Д'});
  if(reply.state==='HOLD')return Object.freeze({state:'HOLD',label:'HOLD · '+String(reply.errorCode||'NATIVE_HANDLER_UNAVAILABLE').slice(0,72),value:'Н/Д'});
  if(reply.state==='STOP_REQUESTED')return Object.freeze({state:'STOP_REQUESTED',label:'STOP запрошен · подтверждение завершения ожидается',value:'Н/Д'});
  const v=reply.result;
  const models=Array.isArray(v?.models)?v.models.length:null;
  const jobs=Array.isArray(v?.jobs)?v.jobs.length:null;
  const tasks=Array.isArray(v?.tasks)?v.tasks.length:null;
  const count=[models,jobs,tasks].find(SAFE_COUNT);
  const nativeStatus=typeof v?.status==='string'&&/^[A-Za-z0-9 _.:/-]{1,56}$/.test(v.status)?v.status:'NATIVE ACK';
  return Object.freeze({state:'COMPLETED',label:'Ответ ядра · '+nativeStatus,value:count===undefined?'Н/Д':String(count)});
}
export function isTrustedInstallerEvent(raw,now=Date.now()){
  if(!raw||raw.schema!=='NOX-INSTALLER-EVENT-v3'||raw.evidence_verified!==true||
    !ID.test(raw.event_id||'')||!ID.test(raw.run_id||'')||!ID.test(raw.task_id||'')||
    !ID.test(raw.action_id||'')||!Number.isSafeInteger(raw.event_sequence)||raw.event_sequence<1||
    !/^[0-9a-f]{64}$/i.test(raw.receipt_sha256||''))return false;
  const ts=Date.parse(raw.timestamp_utc);
  return Number.isFinite(ts)&&ts<=now+5000&&now-ts>=0&&now-ts<=30000;
}
/**
 * Mount only after mountSelfBuilderMenuV2 created its ten existing DOM buttons.
 * Restricted data goes through request() from the already mounted original OneHost.
 */
export function mountR11WowMenu({root,documentRef,windowRef,request,scope,now=Date.now,schedule=setTimeout,cancel=clearTimeout}={}){
  if(!root||typeof request!=='function'||typeof scope!=='function'||!documentRef||!windowRef||
    root.closest?.('[data-nox-page="home"]')||root.dataset?.noxPage==='home'||
    root.querySelector?.('[data-nox-r11="mounted"]'))throw Error('NOX_R11_ONEHOST_ORIGINAL_MENU_REQUIRED');
  const doc=documentRef,view=windowRef;
  const worlds=Array.from(root.querySelectorAll('[data-nox-world]'));
  const ids=worlds.map(x=>x.dataset?.noxWorld);
  if(worlds.length!==10||new Set(ids).size!==10||R11_WORLD_IDS.some(id=>!ids.includes(id)))
    throw Error('NOX_R11_TEN_ORIGINAL_SUBWORLDS_REQUIRED');
  const statusHost=doc.getElementById('status')||root;
  if(statusHost.querySelector?.('[data-nox-r11-ticker]'))throw Error('NOX_R11_ONE_TICKER_ONLY');
  const clean=[],busy=new Set();let dead=false,epoch=0,staleTimer=null,last=null;
  const node=(tag,cls,text='')=>{const e=doc.createElement(tag);if(cls)e.className=cls;e.textContent=text;return e;};
  const add=(target,event,fn,options)=>{target.addEventListener(event,fn,options);clean.push(()=>target.removeEventListener(event,fn,options));};
  const panel=node('section','nox-r11-cockpit');panel.dataset.noxR11='mounted';
  const head=node('div','nox-r11-head');
  head.append(node('h3','nox-r11-title','NOX · командный центр'),node('span','nox-r11-source','ONEHOST · NATIVE ONLY'));
  const lead=node('p','nox-r11-lead','Модели, обучение, знания и саморазвитие. Только реальные ответы ядра; неподтверждённое — HOLD.');
  const grid=node('div','nox-r11-actions');
  const feedback=node('p','nox-r11-feedback','Нет подтверждённых данных · Н/Д');feedback.setAttribute('role','status');feedback.setAttribute('aria-live','polite');
  const metrics=node('div','nox-r11-metrics');
  const labels=[['model','МОДЕЛИ'],['learning','ОБУЧЕНИЕ'],['system','СИСТЕМА']];
  const metricValues=new Map();
  for(const [id,label] of labels){const cell=node('div','nox-r11-metric');cell.append(node('span','nox-r11-metric-label',label));const out=node('strong','nox-r11-metric-value','Н/Д');cell.append(out);metrics.append(cell);metricValues.set(id,out);}
  const ticker=node('section','nox-r11-ticker');ticker.dataset.noxR11Ticker='true';ticker.dataset.state='unknown';
  const led=node('span','nox-r11-led');led.setAttribute('aria-hidden','true');
  const tickerText=node('span','nox-r11-ticker-text','NOX · нет подтверждённых событий');tickerText.setAttribute('role','status');tickerText.setAttribute('aria-live','polite');
  const tickerOpen=node('button','nox-r11-ticker-open','К панели');tickerOpen.type='button';tickerOpen.hidden=true;
  ticker.append(led,tickerText,tickerOpen);
  const searchButton=node('button','nox-r11-search','⌕ Быстрый поиск · Ctrl+K');searchButton.type='button';
  const palette=node('section','nox-r11-palette');palette.dataset.noxR11Palette='true';palette.hidden=true;
  const search=node('input','nox-r11-palette-input');search.type='search';search.placeholder='Поиск по существующим разделам';search.setAttribute('aria-label','Поиск разделов NOX');
  const results=node('div','nox-r11-palette-results');
  const close=node('button','nox-r11-palette-close','Закрыть · Esc');close.type='button';
  palette.append(search,results,close);
  panel.append(head,lead,searchButton,metrics,grid,feedback,palette);
  root.prepend(panel);statusHost.append(ticker);
  root.classList.add('nox-r11-enhanced');
  for(const world of worlds)world.classList.add('nox-r11-world');
  const stale=()=>{if(dead)return;last=null;ticker.dataset.state='stale';tickerText.textContent='Н/Д · подтверждённые события устарели';tickerOpen.hidden=true;};
  function displayNative(reply,action){
    if(dead)return;
    const data=projectNativeReply(reply);
    feedback.textContent=action.label+' · '+data.label;
    feedback.dataset.state=data.state;
    if(data.state==='COMPLETED'){
      if(action.id==='models'||action.id==='chat-model')metricValues.get('model').textContent=data.value;
      if(action.id==='learning'||action.id==='plan')metricValues.get('learning').textContent=data.value;
      if(action.id==='gpu'||action.id==='models-check')metricValues.get('system').textContent=data.value;
    }
    ticker.dataset.state=data.state==='COMPLETED'?'verified':data.state==='HOLD'?'hold':'pending';
    tickerText.textContent=action.label+' · '+data.label;
    if(staleTimer!==null)cancel(staleTimer);
    staleTimer=schedule(stale,30000);
    last=action;
    tickerOpen.hidden=false;
  }
  async function execute(action){
    if(dead||busy.has(action.id))return;
    const s=scope();
    const payload=action.action?{action:action.action,...s}:{};
    if(action.action&&(!ID.test(s?.core_id||'')||!ID.test(s?.persona_id||''))){
      feedback.textContent='HOLD · выберите ядро и персонажа для AI-функции';return;
    }
    const source=buttons.get(action.id);
    busy.add(action.id);if(source)source.disabled=true;
    feedback.textContent=action.label+' · REQUESTED, ожидание native ACK';
    const thisEpoch=++epoch;
    try{
      const reply=await request(action.route,payload);
      if(dead||thisEpoch!==epoch)return;
      const current=scope();
      if(action.action&&(current.core_id!==s.core_id||current.persona_id!==s.persona_id))return;
      displayNative(reply,action);
    }catch(error){if(!dead&&thisEpoch===epoch){
      feedback.dataset.state='HOLD';feedback.textContent=action.label+' · HOLD · '+(error?.message==='TIMEOUT'?'нет ответа ядра':'неподтверждённый запрос');
      ticker.dataset.state='hold';tickerText.textContent=feedback.textContent;
    }}finally{busy.delete(action.id);if(!dead&&source)source.disabled=false;}
  }
  const buttons=new Map();
  for(const action of R11_READ_ACTIONS){
    const b=node('button','nox-r11-action',action.label);b.type='button';b.dataset.nativeRoute=action.route;
    b.dataset.actionId=action.action||'';
    add(b,'click',()=>{void execute(action)});grid.append(b);buttons.set(action.id,b);
  }
  const stop=node('button','nox-r11-stop','STOP · остановить локальный ответ');stop.type='button';
  add(stop,'click',async()=>{
    if(dead||busy.has('stop'))return;
    busy.add('stop');stop.disabled=true;
    try{displayNative(await request('chat.stop',{}),{label:'STOP',id:'stop'});}
    catch{if(!dead){feedback.textContent='HOLD · STOP не подтверждён нативным ядром';ticker.dataset.state='hold';}}
    finally{busy.delete('stop');if(!dead)stop.disabled=false;}
  });grid.append(stop);
  function findWorlds(query){
    const q=String(query||'').trim().toLocaleLowerCase('ru');
    return worlds.filter(w=>String(w.textContent||'').toLocaleLowerCase('ru').includes(q));
  }
  function renderPalette(){
    results.replaceChildren();for(const world of findWorlds(search.value)){
      const b=node('button','nox-r11-palette-item',world.textContent?.trim()||world.dataset.noxWorld);b.type='button';
      // Do not click hidden destinations in another parent world: original physical navigation owns that transition.
      const hidden=world.hidden===true||world.closest?.('[hidden]');
      b.disabled=!!hidden;b.title=hidden?'Выберите соответствующий основной раздел':'Открыть существующий раздел';
      add(b,'click',()=>{palette.hidden=true;world.click();});results.append(b);
    }
    if(results.children.length===0)results.append(node('p','nox-r11-empty','Совпадений нет'));
  }
  function togglePalette(value){palette.hidden=!value;if(value){search.value='';renderPalette();search.focus();}else searchButton.focus();}
  add(searchButton,'click',()=>togglePalette(true));add(search,'input',renderPalette);add(close,'click',()=>togglePalette(false));
  add(doc,'keydown',event=>{
    if(dead)return;
    if((event.ctrlKey||event.metaKey)&&event.key?.toLowerCase()==='k'&&!event.altKey){
      event.preventDefault();togglePalette(palette.hidden);return;
    }
    if(event.key==='Escape'&&!palette.hidden){event.preventDefault();togglePalette(false);}
  });
  add(tickerOpen,'click',()=>{if(dead||!last)return;root.scrollIntoView?.({behavior:view.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches?'instant':'smooth',block:'start'});});
  return Object.freeze({snapshot:()=>Object.freeze({worldCount:worlds.length,actions:buttons.size,verified:ticker.dataset.state==='verified',hasNativeProof:ticker.dataset.state==='verified'}),
    destroy(){if(dead)return;dead=true;if(staleTimer!==null)cancel(staleTimer);for(const un of clean.reverse())try{un()}catch{};
      for(const w of worlds)w.classList.remove('nox-r11-world');root.classList.remove('nox-r11-enhanced');panel.remove();ticker.remove();}});
}
