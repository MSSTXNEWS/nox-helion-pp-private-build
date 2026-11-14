/** NOX WOW R11/MENU10: additive original-scene layer. Only trusted D02 native bus. */
const ID=/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const ROUTES=Object.freeze({'task.started':'progress','task.progress':'model-library','training.step':'learning-proofs','checkpoint.saved':'learning-proofs','task.completed':'learning-proofs','model.stopped':'progress'});
const LABELS=Object.freeze({'task.started':'Задание запущено','task.progress':'Загрузка модели','training.step':'Шаг обучения','checkpoint.saved':'Контрольная точка сохранена','task.completed':'Задача завершена','model.stopped':'Выполнение остановлено'});
export function asTrustedWowEvent(raw,now=Date.now()){
 if(!raw||raw.schema!=='NOX-INSTALLER-EVENT-v3'||raw.evidence_verified!==true||!Object.hasOwn(ROUTES,raw.event_type)||!ID.test(raw.event_id)||!ID.test(raw.run_id)||!ID.test(raw.task_id)||!ID.test(raw.action_id)||!['P01','P02','P03','P04','P05','E06'].includes(raw.package_id)||!Number.isSafeInteger(raw.event_sequence)||raw.event_sequence<1||!/^[0-9a-f]{64}$/i.test(raw.receipt_sha256||''))return null;
 if(raw.event_type==='task.progress'&&(raw.package_id!=='P03'||!/^(pull|download|model[._-](pull|download))/.test(raw.action_id)))return null;
 if(['training.step','checkpoint.saved'].includes(raw.event_type)&&raw.package_id!=='P04')return null;
 if(raw.event_type==='model.stopped'&&!['P03','P04'].includes(raw.package_id))return null;
 if(raw.event_type==='task.completed'&&(raw.package_id!=='P04'||!/^rag[._-](index|ingest|reindex)/.test(raw.action_id)))return null;
 const t=Date.parse(raw.timestamp_utc);
 if(!Number.isFinite(t)||t>now+5000||now-t>30000)return null;
 const progress=Number.isSafeInteger(raw.numerator)&&Number.isSafeInteger(raw.denominator)&&raw.denominator>0&&raw.numerator>=0&&raw.numerator<=raw.denominator;
 if(raw.numerator!=null&&!progress)return null;
 return Object.freeze({id:raw.event_id,runId:raw.run_id,sequence:raw.event_sequence,route:ROUTES[raw.event_type],label:LABELS[raw.event_type],percent:progress?Math.round(100*raw.numerator/raw.denominator):null});
}
export function mountNoxWowVisualLayers({root,orb=null,menuWorlds=[],panels=[],notificationHost,nativeBus,routePort,now=Date.now,schedule=setTimeout,cancel=clearTimeout}={}){
 if(!root?.ownerDocument||typeof root.contains!=='function'||!notificationHost||!root.contains(notificationHost)||typeof nativeBus?.subscribe!=='function'||typeof routePort?.isAvailable!=='function'||typeof routePort?.invokeRoute!=='function'||!Array.isArray(menuWorlds)||!Array.isArray(panels)||(orb&&!root.contains(orb))||[...menuWorlds,...panels].some(el=>!root.contains(el)))throw Error('NOX_EXISTING_TRUSTED_VISUAL_HOST_REQUIRED');
 if(root.querySelector?.('[data-nox-wow-r11="true"]'))throw Error('NOX_WOW_R11_ALREADY_MOUNTED');
 const doc=root.ownerDocument,win=doc.defaultView,clean=[],seen=new Set(),seq=new Map();
 let dead=false,timer=null,active=null;
 const decorate=(el,cls)=>{if(el){el.classList.add(cls);clean.push(()=>el.classList.remove(cls));}};
 decorate(root,'nox-wow-r11');decorate(orb,'nox-wow-r11-sun');
 for(const el of menuWorlds)decorate(el,'nox-wow-r11-world');
 for(const el of panels)decorate(el,'nox-wow-r11-panel');
 const bar=doc.createElement('section');bar.className='nox-wow-r11-ticker';bar.dataset.noxWowR11='true';bar.setAttribute('aria-label','Подтверждённые события NOX');
 const led=doc.createElement('span');led.className='nox-wow-r11-indicator';led.setAttribute('aria-hidden','true');
 const msg=doc.createElement('span');msg.className='nox-wow-r11-message';msg.setAttribute('role','status');msg.setAttribute('aria-live','polite');msg.textContent='Нет подтверждённых системных событий';
 const btn=doc.createElement('button');btn.type='button';btn.className='nox-wow-r11-open';btn.textContent='Открыть';btn.disabled=true;btn.hidden=true;
 bar.append(led,msg,btn);notificationHost.append(bar);clean.push(()=>bar.remove());
 const stale=()=>{if(dead)return;active=null;bar.dataset.state='stale';msg.textContent='События не обновлялись · данных нет';btn.disabled=true;btn.hidden=true;if(orb)delete orb.dataset.noxWowVerifiedPulse;};
 const onNative=raw=>{
  if(dead)return;const ev=asTrustedWowEvent(raw,now());if(!ev)return;
  const prev=seq.get(ev.runId);if(prev!==undefined&&ev.sequence<=prev||seen.has(ev.id))return;
  seq.set(ev.runId,ev.sequence);if(seq.size>64)seq.delete(seq.keys().next().value);
  seen.add(ev.id);if(seen.size>96)seen.delete(seen.values().next().value);
  active=ev;bar.dataset.state='verified';msg.textContent=ev.label+(ev.percent===null?'':' · '+ev.percent+'%');
  let available=false;try{available=routePort.isAvailable(ev.route)===true}catch{}
  btn.disabled=!available;btn.hidden=!available;
  if(timer!==null)cancel(timer);timer=schedule(stale,30000);
  if(orb)orb.dataset.noxWowVerifiedPulse='true';
 };
 const unsub=nativeBus.subscribe(onNative);if(typeof unsub!=='function'){bar.remove();throw Error('NOX_NATIVE_UNSUBSCRIBE_REQUIRED');}clean.push(unsub);
 const open=async()=>{if(dead||!active||btn.disabled)return;const route=active.route;
  try{if(routePort.isAvailable(route)!==true){btn.disabled=true;return;}btn.disabled=true;
    const r=await routePort.invokeRoute(Object.freeze({routeId:route,origin:'NOX_WOW_R11_TICKER'}));
    if(!dead&&(r?.ok!==true||r.routeId!==route||!ID.test(r.receiptId))){bar.dataset.state='hold';msg.textContent='Переход не подтверждён NOX';}
  }catch{if(!dead){bar.dataset.state='hold';msg.textContent='Маршрут недоступен';}}
  finally{if(!dead&&active){try{btn.disabled=routePort.isAvailable(route)!==true}catch{btn.disabled=true}}}
 };
 btn.addEventListener('click',open);clean.push(()=>btn.removeEventListener('click',open));
 if(orb){
  const pointer=e=>{if(dead||doc.hidden||win?.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches===true)return;
   const b=orb.getBoundingClientRect?.();if(!b?.width||!b?.height)return;
   const x=Math.max(-1,Math.min(1,(e.clientX-b.left-b.width/2)/(b.width/2)));
   const y=Math.max(-1,Math.min(1,(e.clientY-b.top-b.height/2)/(b.height/2)));
   orb.style.setProperty('--nox-wow-r11-x',(x*3).toFixed(2)+'px');orb.style.setProperty('--nox-wow-r11-y',(y*3).toFixed(2)+'px');
  };
  const reset=()=>{orb.style.removeProperty('--nox-wow-r11-x');orb.style.removeProperty('--nox-wow-r11-y');};
  orb.addEventListener('pointermove',pointer,{passive:true});orb.addEventListener('pointerleave',reset);
  clean.push(()=>orb.removeEventListener('pointermove',pointer),()=>orb.removeEventListener('pointerleave',reset),()=>{reset();delete orb.dataset.noxWowVerifiedPulse;});
 }
 return Object.freeze({snapshot:()=>Object.freeze({verifiedEvents:seen.size,tickerState:bar.dataset.state||'no-data',activeRoute:active?.route||null}),destroy(){if(dead)return;dead=true;if(timer!==null)cancel(timer);for(const fn of clean.reverse())try{fn()}catch{};seen.clear();seq.clear();}});
}
