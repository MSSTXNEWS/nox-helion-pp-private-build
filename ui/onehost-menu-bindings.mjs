/** Connect existing MENU V2 surfaces to the ONE native WebView2 owner.
 * No HTTP transport, second host, data store, permissions or simulated sensors.
 */
import {mountSelfBuilderMenuV2, SELFBUILDER_MENU} from './selfbuilder-menu-v2.mjs';

export const CORE_RUNTIME_IDS=Object.freeze(Object.fromEntries(
  ['consciousness','atlas','reflection','nexus','forge','core','voice','persona'].map(x=>[x,'core.'+x])));
export const PERSONA_RUNTIME_IDS=Object.freeze({kairen:'persona.kairen_voss',adrian:'persona.adrian_marrow',
  leon:'persona.leon_ardis',elina:'persona.elina_veil',cassien:'persona.kassien_veir'});
export function canonicalChatContext(core,persona){
  const coreId=CORE_RUNTIME_IDS[String(core).toLowerCase()]||
    Object.values(CORE_RUNTIME_IDS).find(x=>x===core)||'';
  const personaId=PERSONA_RUNTIME_IDS[persona]||Object.values(PERSONA_RUNTIME_IDS).find(x=>x===persona)||'';
  return {core_id:coreId,persona_id:personaId};
}
const ACTIONS = new Set(SELFBUILDER_MENU.map(x => x.actionId));
const ROUTES = new Set(['helion.chat','chat.history','chat.stop','chat.model','chat.commands',
  'models.catalog','models.queue','models.preflight','models.pull','models.cancel','models.retry','models.gguf.import','gpu.preflight','training.start']);
const AUTHORITY = new Set(['tenant','principal','windows_sid','session_id','scopes',
  'private_approved','native_approve','nativeConsent','admin']);

export function createNativeMenuClient({webview,cryptoRef=globalThis.crypto,
  setTimer=setTimeout,clearTimer=clearTimeout,timeoutMs=65000}={}) {
  if (!webview?.postMessage || !webview?.addEventListener || !cryptoRef?.getRandomValues)
    throw Error('NOX_NATIVE_HOST_REQUIRED');
  const pending = new Map(); let disposed=false;
  function receive(event) {
    const v=event?.data;
    if(!v || typeof v!=='object' || !['p02NativeResult','p02NativeEvent'].includes(v.kind))return;
    const p=pending.get(v.requestId);
    if(!p || v.routeId!==p.route)return;
    if(v.kind==='p02NativeEvent'){
      if(v.state==='STREAMING'&&v.data?.route===p.route&&typeof v.data.delta==='string'&&v.data.delta.length<=65536)p.onEvent?.(v.data);
      return;
    }
    if(!['COMPLETED','STOP_REQUESTED','HOLD'].includes(v.state))return;
    pending.delete(v.requestId);clearTimer(p.timer);
    p.resolve(v);
  }
  webview.addEventListener('message',receive);
  return Object.freeze({
    request(route,payload={},onEvent=null) {
      if(disposed)return Promise.reject(Error('NOX_NATIVE_CLIENT_DISPOSED'));
      if(!ROUTES.has(route) || !payload || typeof payload!=='object' || Array.isArray(payload) ||
        Object.keys(payload).some(k=>AUTHORITY.has(k)))return Promise.reject(Error('NOX_NATIVE_REQUEST_DENIED'));
      if(route==='chat.commands' && !ACTIONS.has(payload.action) && payload.action!=='selfbuilder.capabilities')
        return Promise.reject(Error('NOX_MENU_ACTION_DENIED'));
      const modelKey=['models.pull','models.gguf.import'].includes(route)?'modelTag':
        ['models.cancel','models.retry'].includes(route)?'jobId':null;
      if(modelKey&&(Object.keys(payload).length!==1||typeof payload[modelKey]!=='string'||!payload[modelKey]))
        return Promise.reject(Error('NOX_NATIVE_MODEL_SELECTION_REQUIRED'));
      if((route==='training.start'||route==='chat.commands'&&payload.action?.startsWith('training.'))&&
        (typeof payload.job_id!=='string'||!payload.job_id||Object.keys(payload).some(k=>!['action','job_id','core_id','persona_id'].includes(k))))
        return Promise.reject(Error('NOX_APPROVED_TRAINING_JOB_REQUIRED'));
      if(pending.size>=32)return Promise.reject(Error('NOX_NATIVE_REQUEST_LIMIT'));
      const bytes=new Uint8Array(16);cryptoRef.getRandomValues(bytes);
      const id=Array.from(bytes,x=>x.toString(16).padStart(2,'0')).join('');
      if(pending.has(id))return Promise.reject(Error('NOX_NATIVE_NONCE_COLLISION'));
      return new Promise((resolve,reject)=>{
        const timer=setTimer(()=>{pending.delete(id);reject(Error('TIMEOUT'));},timeoutMs);
        pending.set(id,{route,resolve,reject,timer,onEvent});
        try{webview.postMessage({kind:'p02.native',requestId:id,routeId:route,payload});}
        catch(error){pending.delete(id);clearTimer(timer);reject(error);}
      });
    },
    destroy(){
      if(disposed)return;disposed=true;webview.removeEventListener?.('message',receive);
      for(const p of pending.values()){clearTimer(p.timer);p.reject(Error('NOX_DOCUMENT_CLOSED'));}
      pending.clear();
    }
  });
}

export function mountOneHostMenu({documentRef=globalThis.document,windowRef=globalThis.window}={}) {
  const doc=documentRef,view=windowRef;
  if(!doc||!view)throw Error('NOX_MENU_DOCUMENT_REQUIRED');
  // The endpoint is accessible only at the original native virtual origin.
  if(view.location?.origin!=='https://nox.local')return null;
  const native=view.chrome?.webview;
  if(!native)return null;
  const client=createNativeMenuClient({webview:native,cryptoRef:view.crypto});
  let states=Object.create(null),trainingJobs=[],disposed=false,menu=null;
  const root=doc.getElementById('menu-detail');
  const status=doc.createElement('p');status.className='nox-sb-feedback';
  status.setAttribute('role','status');status.setAttribute('aria-live','polite');
  status.textContent='NOX · ожидание подтверждённого ответа';
  const detail=doc.createElement('pre');detail.className='nox-sb-result';detail.hidden=true;
  const actions=doc.createElement('div');actions.className='nox-sb-grid';actions.dataset.noxNativeActions='true';
  const statusRoot=root||doc.getElementById('status');statusRoot?.append(status,detail,actions);
  const display=v=>{
    if(disposed)return;
    const data=v.result;actions.replaceChildren();
    function action(label,route,key,id){
      const b=doc.createElement('button');b.type='button';b.className='nox-sb-tile';b.textContent=label;
      b.dataset.nativeRoute=route;b.dataset.nativeKey=key;b.dataset.nativeValue=id;actions.append(b);
    }
    if(v.state==='COMPLETED'&&Array.isArray(data?.models))for(const model of data.models){
      if(model?.downloadEligible!==true||!Array.isArray(model.artifacts))continue;
      for(const artifact of model.artifacts){
        if(typeof artifact?.exactTag!=='string'||!artifact.exactTag)continue;
        action('Скачать · '+artifact.exactTag,'models.pull','modelTag',artifact.exactTag);
        action('Импортировать GGUF · '+artifact.exactTag,'models.gguf.import','modelTag',artifact.exactTag);
      }
    }
    if(v.state==='COMPLETED'&&Array.isArray(data?.jobs))for(const job of data.jobs){
      if(typeof job?.id!=='string')continue;
      if(['queued','running','downloading'].includes(String(job.state).toLowerCase()))action('Отменить · '+job.id,'models.cancel','jobId',job.id);
      if(['failed','cancelled','canceled'].includes(String(job.state).toLowerCase()))action('Повторить · '+job.id,'models.retry','jobId',job.id);
    }
    if(v.routeId?.startsWith('models.'))action('Обновить очередь загрузки','models.queue','','');
    detail.hidden=!data;detail.textContent=data?JSON.stringify(data,null,2):'';
    status.textContent=v.state==='HOLD'?'HOLD · '+(v.errorCode||'NATIVE_HANDLER_UNAVAILABLE'):
      v.state==='STOP_REQUESTED'?'STOP REQUESTED · ожидается завершение ядра':
      'NOX · '+(data?.status||v.state);
  };
  if(root){
    menu=mountSelfBuilderMenuV2({root,documentRef:doc,getCurrentSection:()=>doc.getElementById('detail-title')?.textContent?.trim(),
      ownerApprovedRoute:(section,route,action)=>SELFBUILDER_MENU.some(x=>x.section===section&&x.routeId===route&&x.actionId===action),
      getTrustedState:action=>states[action],getTrainingJobs:()=>trainingJobs,
      invokeNative:async request=>{
        root.append(status,detail,actions);detail.hidden=true;
        const scope=context();
        if(!scope.core_id||!scope.persona_id)throw Error('SELECT_CORE_AND_PERSONA');
        const route=request.actionId==='selfbuilder.train.request'?'training.start':'chat.commands';
        const result=await client.request(route,{...(route==='chat.commands'?{action:request.actionId}:{}),...scope,
          ...(request.task?{task:request.task}:{}),...(request.job_id?{job_id:request.job_id}:{})});display(result);
        return result.state==='COMPLETED'?{...result.result,ack:true}:{ack:false,errorCode:result.errorCode};
      }});
  }
  const sectionObserver=root&&view.MutationObserver?new view.MutationObserver(()=>menu?.refresh()):null;
  const title=doc.getElementById('detail-title');
  if(title)sectionObserver?.observe(title,{childList:true,characterData:true,subtree:true});
  async function refresh(){
    try{
      const scope=context();
      if(!scope.core_id||!scope.persona_id)throw Error('SELECT_CORE_AND_PERSONA');
      const reply=await client.request('chat.commands',{action:'selfbuilder.capabilities',...scope});
      if(disposed)return;
      states=Object.create(null);trainingJobs=[];
      if(reply.state==='COMPLETED'&&Array.isArray(reply.result?.trainingJobs))trainingJobs=reply.result.trainingJobs.filter(x=>typeof x?.id==='string');
      if(reply.state==='COMPLETED' && reply.result?.actions && typeof reply.result.actions==='object')
        for(const action of ACTIONS){
          const s=reply.result.actions[action];
          if(s&&typeof s==='object')states[action]={available:s.available===true,
            status:typeof s.status==='string'?s.status:'HOLD',ownerConsent:s.ownerConsent===true,requiresNativeConsent:s.requiresNativeConsent===true};
        }
      menu?.refresh();display(reply);
    }catch(error){if(!disposed){states=Object.create(null);menu?.refresh();status.textContent=(error.message==='TIMEOUT'?'TIMEOUT':'HOLD')+' · нет ответа ядра';}}
  }
  // Bind only explicit existing controls; keep their source geometry and art.
  // Capture avoids double dispatch to the old diagnostic placeholder handler.
  const controls=new Map([
    ['model-center','models.catalog'],['pc-check','models.preflight'],
    ['training-diagnostic','gpu.preflight'],
    ['drive-log','chat.commands'],['chat-stop','chat.stop']
  ]);
  const value=id=>doc.getElementById(id)?.value||'';
  const context=()=>canonicalChatContext(value('chat-core'),value('chat-persona'));
  const chatStatus=message=>{const target=doc.getElementById('chat-state');if(target)target.textContent=message;};
  let chatBusy=false;
  async function sendChat(){
    const scope=context(),text=value('chat-input').trim(),model=value('chat-model');
    if(!scope.core_id||!scope.persona_id||!text||!model){chatStatus('HOLD · выберите ядро, персону, модель и введите сообщение');return;}
    if(chatBusy)return;chatBusy=true;
    const send=doc.getElementById('chat-send'),stop=doc.getElementById('chat-stop');
    if(send)send.disabled=true;if(stop)stop.disabled=false;
    const row=doc.createElement('p');row.dataset.noxNativeChat='answer';
    doc.getElementById('chat-log')?.append(row);chatStatus('REQUESTED · локальное ядро');
    try{
      const reply=await client.request('helion.chat',{text,model,...scope},event=>{
        if(!disposed){row.textContent+=event.delta;chatStatus('STREAMING · локальная модель');}
      });
      if(disposed)return;
      if(reply.state==='COMPLETED'&&typeof reply.result?.answer==='string')row.textContent=reply.result.answer;
      chatStatus(reply.state==='HOLD'?'HOLD · '+(reply.errorCode||'NO_MODEL_REPLY'):reply.result?.done===true?'COMPLETED':'HOLD · ответ не завершён');
    }catch(error){if(!disposed)chatStatus(error.message==='TIMEOUT'?'TIMEOUT · результат не подтверждён, STOP доступен':'HOLD · соединение с ядром');}
    finally{chatBusy=false;if(!disposed){if(send)send.disabled=false;if(stop)stop.disabled=false;}}
  }
  async function models(){
    const select=doc.getElementById('chat-model');if(!select)return;
    try{
      const reply=await client.request('chat.model',{});
      if(disposed||reply.state!=='COMPLETED'||!Array.isArray(reply.result?.models))return;
      select.replaceChildren();
      for(const name of reply.result.models){if(typeof name!=='string')continue;const option=doc.createElement('option');option.value=name;option.textContent=name;select.append(option);}
      if(reply.result.selectedModel)select.value=reply.result.selectedModel;
      const send=doc.getElementById('chat-send');if(send)send.disabled=!select.value;
      chatStatus(select.value?'LOCAL · модель обнаружена':'HOLD · локальная модель не установлена');
    }catch(_){chatStatus('HOLD · модель не обнаружена');}
  }
  async function click(event){
    const button=event.target?.closest?.('button');if(!button||button.disabled)return;
    if(['chat-send','chat-stop'].includes(button.id)&&value('chat-provider')==='OPENAI')return;
    if(button.id==='chat-send'){event.preventDefault();event.stopImmediatePropagation();await sendChat();return;}
    const generated=button.parentElement===actions||button.parentNode===actions;
    const route=controls.get(button.id)||(generated?button.dataset.nativeRoute:null);if(!route)return;
    event.preventDefault();event.stopImmediatePropagation();
    button.closest('section')?.append(status,detail,actions);detail.hidden=true;
    button.disabled=true;status.textContent='REQUESTED · ожидается ответ ядра';
    const payload=generated?(button.dataset.nativeKey?{[button.dataset.nativeKey]:button.dataset.nativeValue}:{}):route==='chat.commands'?{action:'selfbuilder.worker.status',...context()}:{};
    try{display(await client.request(route,payload));}
    catch(error){if(!disposed)status.textContent=(error.message==='TIMEOUT'?'TIMEOUT':'HOLD')+' · запрос не подтверждён';}
    finally{if(!disposed)button.disabled=false;}
  }
  async function change(event){
    if(!['chat-core','chat-persona','chat-model'].includes(event.target?.id)||value('chat-provider')==='OPENAI')return;
    const scope=context();if(!scope.core_id||!scope.persona_id)return;
    event.stopImmediatePropagation();
    try{
      if(event.target.id==='chat-model'){
        const chosen=await client.request('chat.model',{model:value('chat-model'),...scope});
        if(chosen.state!=='COMPLETED'){chatStatus('HOLD · модель не выбрана');return;}
      }
      const reply=await client.request('chat.history',{limit:100,...scope});
      if(disposed)return;
      if(reply.state!=='COMPLETED'||!Array.isArray(reply.result?.messages)){chatStatus('HOLD · история недоступна');return;}
      const log=doc.getElementById('chat-log');if(log){
        log.replaceChildren();for(const row of reply.result.messages){
          if(typeof row?.content!=='string')continue;
          const p=doc.createElement('p');p.textContent=(row.role==='user'?'Вы: ':'NOX: ')+row.content;log.append(p);
        }
      }
      chatStatus('История выбранного ядра и персоны');await refresh();
    }catch(error){if(!disposed)chatStatus(error.message==='TIMEOUT'?'TIMEOUT':'HOLD · история недоступна');}
  }
  doc.addEventListener('click',click,true);doc.addEventListener('change',change,true);
  const close=()=>{
    if(disposed)return;disposed=true;doc.removeEventListener('click',click,true);doc.removeEventListener('change',change,true);
    view.removeEventListener('pagehide',close);sectionObserver?.disconnect();menu?.destroy();status.remove();detail.remove();actions.remove();client.destroy();
  };
  view.addEventListener('pagehide',close,{once:true});
  refresh();models();
  return Object.freeze({refresh,destroy:close});
}
if(typeof document!=='undefined'){
  const boot=()=>{try{mountOneHostMenu();}catch(error){console.warn('NOX MENU HOLD',error.message);}};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
}
