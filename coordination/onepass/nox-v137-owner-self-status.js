/* NOX V137: authenticated LIVE process/identity observation inside Resonance.
 * Existing OneHost only; all measurements from native endpoints. No controls
 * that restart, stop or modify a service. No guessed/fake progress.
 */
(() => {
  'use strict';
  if (window.NOX_NATIVE_OWNER !== true ||
      !/^\/nox-web-v29\/pc\/(?:resonance\.html|v22\/resonance\.template\.html)$/.test(location.pathname) ||
      window.__NOX_V137_SELF_STATUS) return;
  window.__NOX_V137_SELF_STATUS='READ_ONLY';
  const O=(tag,text,className)=>{
    const e=document.createElement(tag);
    if(text!==undefined)e.textContent=text;
    if(className)e.className=className;
    return e;
  };
  const panel=()=>{
    const system=document.getElementById('v24System');
    // V24 has a system drawer; original V22 only has the left sidebar.
    // Keep the same read-only panel on both original Resonance pages.
    const host=system||document.querySelector('.nox-v22-left');
    if(!host)return null;
    if(host.querySelector('[data-nox-self-monitor="v137"]'))
      return host.querySelector('[data-nox-self-monitor="v137"]');
    const s=O('section',undefined,system?'v24-block v24-glass':'nox-v22-card panel');
    s.dataset.noxSelfMonitor='v137';
    const h=O('h2','NOX · состояние собственных служб');
    const notice=O('p','Сведения появятся после чтения существующего OneHost.','v24-mini');
    notice.dataset.noxMonitorSource='true';
    const list=O('div','Нет проверенной телеметрии.','v24-mini');
    list.dataset.noxMonitorValues='true';
    list.style.whiteSpace='pre-wrap';
    const btn=O('button','Обновить',system?'v24-chip':'nox-v22-btn');
    btn.type='button';
    btn.dataset.action='nox-self-refresh';
    btn.addEventListener('click',()=>{void refresh(s);});
    s.append(h,notice,list,btn);
    host.append(s);
    return s;
  };
  async function json(path){
    const ac=new AbortController();
    const timer=setTimeout(()=>ac.abort(),5000);
    try{
      const r=await window.fetch(path,{method:'GET',credentials:'same-origin',
        cache:'no-store',signal:ac.signal,headers:{Accept:'application/json'}});
      if(!r.ok)throw Error('HTTP_'+r.status);
      const raw=await r.text();
      if(raw.length>64000)throw Error('HOLD_RESPONSE_TOO_LARGE');
      const data=JSON.parse(raw);
      if(!data||typeof data!=='object'||Array.isArray(data))throw Error('HOLD_SCHEMA');
      return data;
    }finally{clearTimeout(timer);}
  }
  const known=x=>Number.isFinite(x)?String(x):'неизвестно';
  function renderNative(d){
    if(d.schema!=='NOX_V137_OWNER_SELF_OBSERVATION_V1')throw Error('HOLD_NATIVE_SELF_SCHEMA');
    const lines=[];
    lines.push('Источник: '+(d.status==='READY'?'OneHost · '+d.collected_at_utc:'HOLD — неполные показания'));
    if(d.service_observation?.state==='OBSERVED'){
      const services=Array.isArray(d.service_observation.services)?d.service_observation.services:[];
      for(const service of services.slice(0,30)){
        if(typeof service.name==='string'&&typeof service.state==='string')
          lines.push('• '+service.name.slice(0,75)+' — '+service.state.slice(0,20));
      }
    }else lines.push('Службы: недоступны');
    if(d.gpu_observation?.state==='OBSERVED'&&Array.isArray(d.gpu_observation.devices)){
      for(const gpu of d.gpu_observation.devices.slice(0,8)){
        lines.push('GPU'+known(gpu.index)+': '+known(gpu.gpu_percent)+'%, VRAM '+
          known(gpu.vram_used_mib)+'/'+known(gpu.vram_total_mib)+' MiB, '+known(gpu.gpu_core_temp_c)+'°C');
      }
    }else lines.push('GPU: неизвестно');
    if(d.s03_observation?.state==='OBSERVED')
      lines.push('S03: '+known(d.s03_observation.fact_rows)+' записей (содержимое не экспортируется)');
    else lines.push('S03: текущая проверка недоступна');
    lines.push('Обучение: '+(d.training?.positive_optimizer_steps_verified===true?
      'проверено нативной квитанцией':'новые шаги оптимизатора не подтверждены'));
    lines.push('STOP: '+(d.stop?.flag_present===true?'обнаружен':d.stop?.flag_present===false?'флаг не обнаружен':'неизвестно'));
    lines.push('Управление службами: только наблюдение; изменения требуют права владельца и квитанции');
    return lines.join('\n');
  }
  async function fallback(){
    // Existing V125 owner routes, no speculative endpoints or synthetic values.
    const wanted=['/api/nox/system/processes','/api/nox/training/status','/api/status'];
    const readings=await Promise.allSettled(wanted.map(json));
    const get=(i)=>readings[i].status==='fulfilled'?readings[i].value:null;
    const proc=get(0),train=get(1),sys=get(2);
    if(!proc&&!train&&!sys)throw Error('HOLD_ALL_NATIVE_ROUTES');
    const lines=['Ограниченные показания существующего OneHost (полный монитор V137 не установлен)'];
    if(proc?.status==='READY'&&proc.source==='PROCFS'){
      lines.push('Процессы: '+known(proc.observed_count)+' всего');
      const counts=proc.categories&&typeof proc.categories==='object'?proc.categories:{};
      for(const name of ['python','llama','supervisor','node']){
        if(Number.isInteger(counts[name]))lines.push('• '+name+': '+counts[name]);
      }
      lines.push('Имена и состояния отдельных служб этим маршрутом не проверяются');
    }else lines.push('Процессы: HOLD/недоступны');
    if(sys?.status==='READY'&&sys.source==='NOX_VAST_PROCFS_NVIDIA_SMI'&&Array.isArray(sys.gpus)){
      for(const x of sys.gpus.slice(0,8))lines.push('GPU'+known(x.index)+
        ': '+known(x.gpu_percent)+'%, VRAM '+known(x.vram_used_gib)+' GiB');
    }else lines.push('GPU: HOLD/недоступно');
    // The V125 status route explicitly DOES NOT verify checkpoint/optimizer.
    if(train)lines.push('Тренер: '+String(train.status||train.state||'HOLD').slice(0,60)+
      ', новые оптимизаторные шаги НЕ подтверждены');
    else lines.push('Тренер: HOLD/недоступен');
    lines.push('S03: не проверялась этим fallback');
    lines.push('STOP, рестарты, процессы Windows: не управляются этим экраном');
    return lines.join('\n');
  }
  let running=false;
  async function refresh(el){
    if(!el||running||document.visibilityState==='hidden')return;
    const note=el.querySelector('[data-nox-monitor-source]');
    const target=el.querySelector('[data-nox-monitor-values]');
    if(!note||!target)return;
    running=true;
    note.textContent='Чтение живых служб…';
    try{
      let description;
      try{
        const observation=await json('/api/nox/self/observations');
        description=renderNative(observation);
      }catch{
        description=await fallback();
      }
      target.textContent=description;
      note.textContent='Обновлено · '+new Date().toLocaleTimeString();
      el.dataset.status='OBSERVED';
    }catch{
      target.textContent='HOLD: нет авторизованных данных OneHost. Не предполагаю, что службы работают или остановлены.';
      note.textContent='Состояние неизвестно';
      el.dataset.status='HOLD';
    }finally{running=false;}
  }
  const attach=()=>{
    const el=panel();
    if(!el)return;
    document.addEventListener('click',e=>{
      const clicked=e.target?.closest?.('[data-action="open-system"]');
      if(clicked)setTimeout(()=>{if(!document.getElementById('v24System')?.hidden)
        void refresh(el);},0);
    },{passive:true});
    setInterval(()=>{
      const drawer=document.getElementById('v24System');
      if(drawer&&!drawer.hidden)void refresh(el);
    },20000);
  };
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',attach,{once:true});
  else attach();
})();
