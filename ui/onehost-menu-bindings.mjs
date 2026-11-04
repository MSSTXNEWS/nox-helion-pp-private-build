/** Connect existing MENU V2 surfaces to the ONE native WebView2 owner.
 * No HTTP transport, second host, data store, permissions or simulated sensors.
 */
import {mountSelfBuilderMenuV2, SELFBUILDER_MENU} from './selfbuilder-menu-v2.mjs';
import {mountWowDesignWorkbench} from './selfbuilder-wow-workbench.mjs';
import {mountR11WowMenu} from './nox-r11-wow.mjs';

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
const ACTIONS = new Set([...SELFBUILDER_MENU.map(x=>x.actionId),
  'selfbuilder.background.status','selfbuilder.background.enable','selfbuilder.background.disable',
  'selfbuilder.design.suggest','selfbuilder.design.review','selfbuilder.design.approve',
  'selfbuilder.activator.status','selfbuilder.a1.status','selfbuilder.a1.boot',
  'selfbuilder.a1.tick','selfbuilder.propose']);
const ROUTES = new Set(['helion.chat','chat.history','chat.stop','chat.model','chat.commands',
  'models.catalog','models.queue','models.preflight','models.pull','models.cancel','models.retry','models.gguf.import','gpu.preflight','training.start','system.autostart','browser.open','browser.navidle','menu.dispatch','menu.binding']);
const AUTHORITY = new Set(['tenant','principal','windows_sid','session_id','scopes',
  'private_approved','native_approve','nativeConsent','admin']);

export function createNativeMenuClient({webview,cryptoRef=globalThis.crypto,
  setTimer=setTimeout,clearTimer=clearTimeout,timeoutMs=65000}={}) {
  if (!webview?.postMessage || !webview?.addEventListener || !cryptoRef?.getRandomValues)
    throw Error('NOX_NATIVE_HOST_REQUIRED');
  const pending = new Map(); let disposed=false;
  function receive(event) {
    // WebView2 host messages have source === chrome.webview and are UA-trusted.
    // Ignore renderer-dispatched MessageEvents even if they copy a request nonce.
    if (event?.isTrusted !== true || event.source !== webview) return;
    const v=event?.data;
    if(!v || typeof v!=='object' || !['p02NativeResult','p02NativeEvent'].includes(v.kind))return;
    const p=pending.get(v.requestId);
    if(!p || v.routeId!==p.route)return;
    if(v.kind==='p02NativeEvent'){
      if(!p.timedOut&&v.state==='STREAMING'&&v.data?.route===p.route&&typeof v.data.delta==='string'&&v.data.delta.length<=65536)p.onEvent?.(v.data);
      return;
    }
    const queueAck=['models.pull','models.retry','models.gguf.import'].includes(p.route) &&
      ['QUEUED','IN_PROGRESS'].includes(v.state);
    if(!queueAck && !['COMPLETED','STOP_REQUESTED','HOLD'].includes(v.state))return;
    pending.delete(v.requestId);clearTimer(p.timer);
    if(p.timedOut){p.onTerminal?.(v);return;}
    p.resolve(v);
  }
  webview.addEventListener('message',receive);
  return Object.freeze({
    request(route,payload={},onEvent=null,onTerminal=null) {
      if(disposed)return Promise.reject(Error('NOX_NATIVE_CLIENT_DISPOSED'));
      if(!ROUTES.has(route) || !payload || typeof payload!=='object' || Array.isArray(payload) ||
        Object.keys(payload).some(k=>AUTHORITY.has(k)))return Promise.reject(Error('NOX_NATIVE_REQUEST_DENIED'));
      if(route==='system.autostart' &&
        (Object.keys(payload).length!==1 || typeof payload.enabled!=='boolean'))
        return Promise.reject(Error('NOX_AUTOSTART_BOOLEAN_REQUIRED'));
      if(route==='browser.open') {
        // Syntax gate only; native Windows owner still enforces exact host/ACL.
        let accepted=false;
        if(Object.keys(payload).length===1 && typeof payload.url==='string' &&
           payload.url.length<=2048 && !/\s/.test(payload.url)) {
          try {
            const target=new URL(payload.url);
            accepted=target.protocol==='https:' && target.port==='' &&
              !target.username && !target.password && !!target.hostname;
          } catch { /* Malformed URL is never forwarded. */ }
        }
        if(!accepted)return Promise.reject(Error('NOX_BROWSER_URL_POLICY_HOLD'));
      }
      if(route==='chat.commands' && !ACTIONS.has(payload.action) && payload.action!=='selfbuilder.capabilities')
        return Promise.reject(Error('NOX_MENU_ACTION_DENIED'));
      const modelKey=['models.pull','models.gguf.import'].includes(route)?'modelTag':
        ['models.cancel','models.retry'].includes(route)?'jobId':null;
      if(modelKey&&(Object.keys(payload).length!==1||typeof payload[modelKey]!=='string'||!payload[modelKey]))
        return Promise.reject(Error('NOX_NATIVE_MODEL_SELECTION_REQUIRED'));
      if((route==='training.start'||route==='chat.commands'&&payload.action?.startsWith('training.'))&&
        (typeof payload.job_id!=='string'||!payload.job_id||Object.keys(payload).some(k=>!['action','job_id','core_id','persona_id'].includes(k))))
        return Promise.reject(Error('NOX_APPROVED_TRAINING_JOB_REQUIRED'));
      // Reserve bounded native STOP/cancel slots when chat timeouts remain
      // unresolved. A timeout is NOT a native completion or STOP receipt.
      const controlRoute=route==='chat.stop'||route==='models.cancel';
      const activeControls=[...pending.values()].filter(p=>
        p.route==='chat.stop'||p.route==='models.cancel').length;
      if(pending.size>=32 && (!controlRoute||activeControls>=2))
        return Promise.reject(Error('NOX_NATIVE_REQUEST_LIMIT'));
      const bytes=new Uint8Array(16);cryptoRef.getRandomValues(bytes);
      const id=Array.from(bytes,x=>x.toString(16).padStart(2,'0')).join('');
      if(pending.has(id))return Promise.reject(Error('NOX_NATIVE_NONCE_COLLISION'));
      return new Promise((resolve,reject)=>{
        const timer=setTimer(()=>{
          const p=pending.get(id);
          if(route==='helion.chat'&&p){p.timedOut=true;reject(Error('TIMEOUT'));}
          else {pending.delete(id);reject(Error('TIMEOUT'));}
        },timeoutMs);
        pending.set(id,{route,resolve,reject,timer,onEvent,onTerminal,timedOut:false});
        try{webview.postMessage({kind:'p02.native',requestId:id,routeId:route,payload});}
        catch(error){pending.delete(id);clearTimer(timer);reject(Error('NOX_NATIVE_POST_FAILED'));}
      });
    },
    destroy(){
      if(disposed)return;disposed=true;webview.removeEventListener?.('message',receive);
      for(const p of pending.values()){clearTimer(p.timer);p.reject(Error('NOX_DOCUMENT_CLOSED'));}
      pending.clear();
    }
  });
}

// Native COMPLETED is a transport envelope, never owner approval. Preserve the
// existing owner ACK byte-for-byte in meaning, and require S03 provenance before
// advertising a selfbuilder proposal as queued. No authorization is inferred.
export function nativeOwnerActionReceipt(reply,route,action) {
  const owner=reply?.result;
  if(reply?.routeId!==route || reply?.state!=='COMPLETED' ||
     !owner || typeof owner!=='object' || Array.isArray(owner) || owner.ack!==true)
    return {ack:false,errorCode:reply?.errorCode||owner?.errorCode||'NATIVE_ACK_UNCONFIRMED'};
  if(action==='selfbuilder.propose' &&
     (typeof owner.run_id!=='string'||!/^S03-[A-Za-z0-9._:-]{1,128}$/.test(owner.run_id) ||
      typeof owner.source_head!=='string'||!/^[a-f0-9]{40}(?:[a-f0-9]{24})?$/.test(owner.source_head)))
    return {ack:false,errorCode:'S03_PROPOSAL_RECEIPT_UNVERIFIED'};
  return {...owner,ack:true};
}

export function isNativeChatTerminal(reply){
  // Called only AFTER createNativeMenuClient validates a UA-trusted WebView2
  // response with the matching request nonce and exact route. A real native
  // HOLD closes the pending request irrespective of its specific errorCode;
  // STOP_REQUESTED and partial completion must never unlock concurrent chat.
  return reply?.routeId==='helion.chat' &&
    (reply.state==='HOLD'||reply.state==='COMPLETED'&&reply.result?.done===true);
}
export function mountOneHostMenu({documentRef=globalThis.document,windowRef=globalThis.window}={}) {
  const doc=documentRef,view=windowRef;
  if(!doc||!view)throw Error('NOX_MENU_DOCUMENT_REQUIRED');
  // The endpoint is accessible only at the original native virtual origin.
  // Same-origin paths are NOT the native-approved mapped HOME (exact https://nox.local/).
  // Fail closed before subscribing the browser to the existing native IPC transport.
  const loc=view.location;
  if(loc?.origin!=='https://nox.local' || loc.pathname!=='/' ||
     loc.search!=='' || loc.hash!=='')return null;
  const native=view.chrome?.webview;
  if(!native)return null;
  const client=createNativeMenuClient({webview:native,cryptoRef:view.crypto});
  let states=Object.create(null),trainingJobs=[],disposed=false,menu=null;
  let selectionEpoch=0,capabilityEpoch=0,historyEpoch=0,chatBusy=false,stopRequestPending=false;
  const sameSelection=(epoch,scope,model=null)=>{
    const now=context();
    return !disposed&&epoch===selectionEpoch&&value('chat-provider')!=='OPENAI'&&
      scope.core_id===now.core_id&&scope.persona_id===now.persona_id&&
      (model===null||value('chat-model')===model);
  };
  const chatTerminal=isNativeChatTerminal;
  const root=doc.getElementById('menu-detail');
  const status=doc.createElement('p');status.className='nox-sb-feedback';
  status.setAttribute('role','status');status.setAttribute('aria-live','polite');
  status.textContent='NOX · ожидание подтверждённого ответа';
  const detail=doc.createElement('pre');detail.className='nox-sb-result';detail.hidden=true;
  const actions=doc.createElement('div');actions.className='nox-sb-grid';actions.dataset.noxNativeActions='true';
  const statusRoot=root||doc.getElementById('status');statusRoot?.append(status,detail,actions);
  const activatorSection=()=>/(?:развитие|интеллект|систем)/i.test(
    doc.getElementById('detail-title')?.textContent||'');
  const appendActivatorShortcut=()=>{
    for(const button of actions.querySelectorAll?.('[data-nox-activator-shortcut]')||[])button.remove();
    if(!activatorSection())return;
    const button=doc.createElement('button');button.type='button';
    button.className='nox-sb-tile';button.textContent='✦ АКТИВАТОР · найти ИИ, веса, GPU';
    button.dataset.noxActivatorShortcut='1';
    button.dataset.nativeRoute='chat.commands';
    button.dataset.nativeKey='action';
    button.dataset.nativeValue='selfbuilder.activator.status';
    actions.append(button);
  };
  const appendSystemAutostartButtons=()=>{
    for(const button of actions.querySelectorAll?.('[data-native-route="system.autostart"]')||[])button.remove();
    const currentWorld=doc.getElementById('detail-title')?.textContent||'';
    if(!/(?:system|систем)/i.test(currentWorld))return;
    for(const [label,value] of [['Автозапуск NOX · ВКЛ','true'],['Автозапуск NOX · ВЫКЛ','false']]){
      const button=doc.createElement('button');button.type='button';button.className='nox-sb-tile';
      button.textContent=label;button.dataset.nativeRoute='system.autostart';
      button.dataset.nativeKey='enabled';button.dataset.nativeValue=value;actions.append(button);
    }
  };
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
        if(typeof artifact?.tag!=='string'||!artifact.tag)continue;
        action('Скачать · '+artifact.tag,'models.pull','modelTag',artifact.tag);
        action('Импортировать GGUF · '+artifact.tag,'models.gguf.import','modelTag',artifact.tag);
      }
    }
    if(v.state==='COMPLETED'&&Array.isArray(data?.jobs))for(const job of data.jobs){
      if(typeof job?.id!=='string')continue;
      if(['queued','running','downloading'].includes(String(job.state).toLowerCase()))action('Отменить · '+job.id,'models.cancel','jobId',job.id);
      if(['failed','cancelled','canceled'].includes(String(job.state).toLowerCase()))action('Повторить · '+job.id,'models.retry','jobId',job.id);
    }
    if(v.state==='COMPLETED'&&data?.schema==='NOX-ACTIVATOR-WORM-STATUS-v1'){
      for(const item of (Array.isArray(data.models)?data.models:[]).slice(0,40)){
        if(typeof item?.tag!=='string'||typeof item.official_page!=='string')continue;
        action((item.observed_locally?'Обнаружена · ':'Открыть загрузку · ')+item.tag,
          'browser.open','url',item.official_page);
        if(item.download_eligible===true)action('Скачать · '+item.tag,
          'models.pull','modelTag',item.tag);
      }
      for(const item of (Array.isArray(data.modules)?data.modules:[]).slice(0,40)){
        if(typeof item?.name!=='string'||typeof item.official_page!=='string')continue;
        action('Готовый модуль · '+item.name,'browser.open','url',item.official_page);
      }
      action('Проверить очередь P03','models.queue','','');
      action('Проверить GPU','gpu.preflight','','');
      action('Активировать ИИ · согласие владельца','chat.commands','action','selfbuilder.a1.boot');
      action('Саморазвитие · запустить цикл','chat.commands','action','selfbuilder.a1.tick');
      action('Саморазвитие · статус','chat.commands','action','selfbuilder.a1.status');
      action('Первый патч · MENU10/D02/WOW','chat.commands','action','selfbuilder.propose');
    }
    if(v.routeId?.startsWith('models.'))action('Обновить очередь загрузки','models.queue','','');
    appendSystemAutostartButtons();
    appendActivatorShortcut();
    detail.hidden=!data;detail.textContent=data?JSON.stringify(data,null,2):'';
    status.textContent=v.state==='HOLD'?'HOLD · '+(v.errorCode||'NATIVE_HANDLER_UNAVAILABLE'):
      v.state==='STOP_REQUESTED'?'STOP REQUESTED · ожидается завершение ядра':
      'NOX · '+(data?.status||data?.state||v.state);
  };
  if(root){
    menu=mountSelfBuilderMenuV2({root,documentRef:doc,getCurrentSection:()=>doc.getElementById('detail-title')?.textContent?.trim(),
      ownerApprovedRoute:(section,route,action)=>SELFBUILDER_MENU.some(x=>x.section===section&&x.routeId===route&&x.actionId===action),
      getTrustedState:action=>states[action],getTrainingJobs:()=>trainingJobs,
      invokeP03Queue:async()=>{
        root.append(status,detail,actions);detail.hidden=true;
        const reply=await client.request('models.queue',{});
        if(!disposed&&doc.getElementById('detail-title')?.textContent?.trim()==='РАЗВИТИЕ')display(reply);
        return reply.routeId==='models.queue'&&reply.state==='COMPLETED'&&Array.isArray(reply.result?.jobs)
          ? {ack:true,jobs:reply.result.jobs}
          : {ack:false,errorCode:reply.errorCode||'P03_QUEUE_UNAVAILABLE'};
      },
      invokeP03Cancel:async jobId=>{
        const reply=await client.request('models.cancel',{jobId});
        // Native ACK confirms STOP request acceptance, not job termination.
        return reply.routeId==='models.cancel'&&
          (reply.state==='STOP_REQUESTED'||
           (reply.state==='COMPLETED'&&reply.result?.cancelled===true))
          ? {ack:true,state:'STOP_REQUESTED'}
          : {ack:false,errorCode:reply.errorCode||'P03_STOP_UNVERIFIED'};
      },
      invokeNative:async request=>{
        root.append(status,detail,actions);detail.hidden=true;
        const scope=context();
        if(!scope.core_id||!scope.persona_id)throw Error('SELECT_CORE_AND_PERSONA');
        const route=request.actionId==='selfbuilder.train.request'?'training.start':'chat.commands';
        const result=await client.request(route,{...(route==='chat.commands'?{action:request.actionId}:{}),...scope,
          ...(request.task?{task:request.task}:{}),...(request.job_id?{job_id:request.job_id}:{})});display(result);
        return nativeOwnerActionReceipt(result,route,request.actionId);
      }});
  }
  // R11: one cosmetic cockpit on existing, already-mounted MENU10 DOM. No second host.
  // All functional requests are forwarded to the ONE native P02 client with its ACL/consent.
  let r11=null;
  if(root){
    try{r11=mountR11WowMenu({root,documentRef:doc,windowRef:view,nativeEventSource:native,
      request:(route,payload)=>client.request(route,payload),
      scope:()=>canonicalChatContext(doc.getElementById('chat-core')?.value||'',
        doc.getElementById('chat-persona')?.value||'')});}
    catch(error){console.warn('NOX_R11_WOW_HOLD',error?.message||'NATIVE_MENU_NOT_READY');}
  }
  const sectionObserver=root&&view.MutationObserver?new view.MutationObserver(()=>{menu?.refresh();appendSystemAutostartButtons();appendActivatorShortcut();}):null;
  const title=doc.getElementById('detail-title');
  if(title)sectionObserver?.observe(title,{childList:true,characterData:true,subtree:true});
  // One passive local probe on first MENU mount. No download, training or patch.
  if(root)void client.request('chat.commands',{action:'selfbuilder.activator.status'})
    .then(reply=>{if(!disposed&&activatorSection())display(reply);})
    .catch(()=>{if(!disposed&&activatorSection())status.textContent='ACTIVATOR HOLD · локальная проверка недоступна';});
  async function refresh(){
    const epoch=selectionEpoch,run=++capabilityEpoch,scope=context();
    try{
      if(!scope.core_id||!scope.persona_id)throw Error('SELECT_CORE_AND_PERSONA');
      const reply=await client.request('chat.commands',{action:'selfbuilder.capabilities',...scope});
      if(run!==capabilityEpoch||!sameSelection(epoch,scope))return;
      states=Object.create(null);trainingJobs=[];
      if(reply.state==='COMPLETED'&&Array.isArray(reply.result?.trainingJobs))trainingJobs=reply.result.trainingJobs.filter(x=>typeof x?.id==='string');
      if(reply.state==='COMPLETED' && reply.result?.actions && typeof reply.result.actions==='object')
        for(const action of ACTIONS){
          const s=reply.result.actions[action];
          if(s&&typeof s==='object')states[action]={available:s.available===true,
            status:typeof s.status==='string'?s.status:'HOLD',ownerConsent:s.ownerConsent===true,requiresNativeConsent:s.requiresNativeConsent===true};
        }
      menu?.refresh();display(reply);
    }catch(error){if(run===capabilityEpoch&&sameSelection(epoch,scope)){states=Object.create(null);menu?.refresh();status.textContent=(error.message==='TIMEOUT'?'TIMEOUT':'HOLD')+' · нет ответа ядра';}}
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

  // R5: native S03 toggle & proposal review, secondary MENU only, never HOME.
  let wow=null,wowObserver=null;
  if(root){
    const r5request=async(action,extra={})=>{
      const scope=context();
      if(!scope.core_id||!scope.persona_id)throw Error('SELECT_CORE_AND_PERSONA');
      const reply=await client.request('chat.commands',{action,...scope,...extra});
      if(reply.state!=='COMPLETED')throw Error('R5_NATIVE_HOLD');
      return reply.result;
    };
    wow=mountWowDesignWorkbench({
      root,documentRef:doc,
      getProposal:async()=>{
        const data=await r5request('selfbuilder.design.review');
        return data?.schema==='NOX-WOW-DESIGN-REVIEW-v1'?data:null;
      },
      ownerApprove:({proposal_sha256,variant_id})=>{
        if(!/^[a-f0-9]{64}$/.test(proposal_sha256)||
           !/^[a-z][a-z0-9-]{1,79}$/.test(variant_id))
          throw Error('R5_UNVERIFIED_REVIEW_CHOICE');
        return r5request('selfbuilder.design.approve',{proposal_sha256,variant_id});
      },
      getBackgroundState:()=>r5request('selfbuilder.background.status'),
      setBackgroundEnabled:(enabled)=>r5request(enabled?'selfbuilder.background.enable':'selfbuilder.background.disable'),
      onError:()=>{status.textContent='HOLD · саморазвитие: требуется подтверждение NOX';}
    });
    const viewR5=()=>{
      const visible=doc.getElementById('detail-title')?.textContent?.trim()==='РАЗВИТИЕ';
      const panel=root.querySelector('[data-nox-wow-studio="owner-v1"]');
      if(panel)panel.hidden=!visible;
      if(visible)void wow.refresh();
    };
    viewR5();
    if(view.MutationObserver && doc.getElementById('detail-title')){
      wowObserver=new view.MutationObserver(viewR5);
      wowObserver.observe(doc.getElementById('detail-title'),
        {childList:true,characterData:true,subtree:true});
    }
  }
  const chatStatus=message=>{const target=doc.getElementById('chat-state');if(target)target.textContent=message;};
  async function sendChat(){
    const scope=context(),text=value('chat-input').trim(),model=value('chat-model'),epoch=selectionEpoch;
    if(!scope.core_id||!scope.persona_id||!text||!model){chatStatus('HOLD · выберите ядро, персону, модель и введите сообщение');return;}
    if(chatBusy)return;chatBusy=true;
    const send=doc.getElementById('chat-send'),stop=doc.getElementById('chat-stop');
    const visible=()=>sameSelection(epoch,scope,model);
    const release=reply=>{
      if(!chatTerminal(reply))return;
      chatBusy=false;
      if(!disposed){
        if(send)send.disabled=!value('chat-model');
        if(stop)stop.disabled=false;
        if(visible()&&reply.state==='COMPLETED'){
          if(typeof reply.result?.answer==='string')row.textContent=reply.result.answer;
          chatStatus('COMPLETED · локальная модель');
        }
      }
    };
    if(send)send.disabled=true;if(stop)stop.disabled=false;
    const row=doc.createElement('p');row.dataset.noxNativeChat='answer';
    doc.getElementById('chat-log')?.append(row);if(visible())chatStatus('REQUESTED · локальное ядро');
    try{
      const reply=await client.request('helion.chat',{text,model,...scope},event=>{
        if(visible()&&row.isConnected){row.textContent+=event.delta;chatStatus('STREAMING · локальная модель');}
      },release);
      if(disposed)return;
      release(reply);
      if(visible()){
        if(reply.state==='COMPLETED'&&typeof reply.result?.answer==='string')row.textContent=reply.result.answer;
        chatStatus(reply.state==='HOLD'?'HOLD · '+(reply.errorCode||'NO_MODEL_REPLY'):reply.result?.done===true?'COMPLETED':'HOLD · ответ не завершён');
      }
    }catch(error){
      if(['NOX_NATIVE_REQUEST_DENIED','NOX_NATIVE_CLIENT_DISPOSED','NOX_NATIVE_REQUEST_LIMIT',
        'NOX_NATIVE_NONCE_COLLISION','NOX_NATIVE_POST_FAILED'].includes(error.message))chatBusy=false;
      if(visible())chatStatus(error.message==='TIMEOUT'?'HOLD · native не завершён, STOP доступен':'HOLD · соединение с ядром');
    }finally{if(!disposed){if(send)send.disabled=chatBusy||!value('chat-model');if(stop)stop.disabled=false;}}
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
    if(button.id==='chat-stop'&&value('chat-provider')==='OPENAI'){
      // Keep legacy OPENAI STOP; additionally signal existing native owner while local execution is UNKNOWN.
      if(chatBusy&&!stopRequestPending){
        stopRequestPending=true;
        void client.request('chat.stop',{}).catch(()=>{}).finally(()=>{stopRequestPending=false;});
      }
      return;
    }
    if(button.id==='chat-send'&&value('chat-provider')==='OPENAI')return;
    if(button.id==='chat-send'){event.preventDefault();event.stopImmediatePropagation();await sendChat();return;}
    const generated=button.parentElement===actions||button.parentNode===actions;
    const route=controls.get(button.id)||(generated?button.dataset.nativeRoute:null);if(!route)return;
    event.preventDefault();event.stopImmediatePropagation();
    button.closest('section')?.append(status,detail,actions);detail.hidden=true;
    if(button.id==='chat-stop'&&stopRequestPending)return;
    if(button.id==='chat-stop')stopRequestPending=true;
    button.disabled=true;status.textContent='REQUESTED · ожидается ответ ядра';
    const task='Сверь существующие D02/HOME/MENU10/WOW и журнал ошибок с текущим SourceLock. Создай ОДИН безопасный дополнительный исходный патч для живой кнопки, раздела или графического эффекта: точный путь, рабочий обработчик, разрешения, STOP, регрессионный тест, SHA и откат. Сохрани исходные 8 астероидов, 10 миров, personas, WebView2, S03/P03, без изменения EXE без независимой приёмки.';
    const payload=generated&&route==='system.autostart'
      ?{enabled:button.dataset.nativeValue==='true'}
      :generated&&route==='chat.commands'&&button.dataset.nativeValue==='selfbuilder.propose'
      ?{action:'selfbuilder.propose',task}
      :generated?(button.dataset.nativeKey?{[button.dataset.nativeKey]:button.dataset.nativeValue}:{})
      :route==='chat.commands'?{action:'selfbuilder.worker.status',...context()}:{};
    try{display(await client.request(route,payload));}
    catch(error){if(!disposed)status.textContent=(error.message==='TIMEOUT'?'TIMEOUT':'HOLD')+' · запрос не подтверждён';}
    finally{if(button.id==='chat-stop')stopRequestPending=false;if(!disposed)button.disabled=false;}
  }
  async function change(event){
    if(!['chat-core','chat-persona','chat-model','chat-provider'].includes(event.target?.id))return;
    ++selectionEpoch;const historyRun=++historyEpoch,epoch=selectionEpoch;
    if(value('chat-provider')==='OPENAI')return;
    const scope=context();if(!scope.core_id||!scope.persona_id)return;
    event.stopImmediatePropagation();
    try{
      if(event.target.id==='chat-model'){
        const chosen=await client.request('chat.model',{model:value('chat-model'),...scope});
        if(historyRun!==historyEpoch||!sameSelection(epoch,scope))return;
        if(chosen.state!=='COMPLETED'){chatStatus('HOLD · модель не выбрана');return;}
      }
      const reply=await client.request('chat.history',{limit:100,...scope});
      if(historyRun!==historyEpoch||!sameSelection(epoch,scope))return;
      if(reply.state!=='COMPLETED'||!Array.isArray(reply.result?.messages)){chatStatus('HOLD · история недоступна');return;}
      const log=doc.getElementById('chat-log');if(log){
        log.replaceChildren();for(const row of reply.result.messages){
          if(typeof row?.content!=='string')continue;
          const p=doc.createElement('p');p.textContent=(row.role==='user'?'Вы: ':'NOX: ')+row.content;log.append(p);
        }
      }
      chatStatus('История выбранного ядра и персоны');await refresh();
    }catch(error){if(historyRun===historyEpoch&&sameSelection(epoch,scope))chatStatus(error.message==='TIMEOUT'?'TIMEOUT':'HOLD · история недоступна');}
  }
  doc.addEventListener('click',click,true);doc.addEventListener('change',change,true);
  const close=()=>{
    if(disposed)return;disposed=true;doc.removeEventListener('click',click,true);doc.removeEventListener('change',change,true);
    view.removeEventListener('pagehide',close);sectionObserver?.disconnect();r11?.destroy();menu?.destroy();wow?.destroy();wowObserver?.disconnect();status.remove();detail.remove();actions.remove();client.destroy();
  };
  view.addEventListener('pagehide',close,{once:true});
  refresh();models();
  return Object.freeze({refresh,destroy:close});
}
if(typeof document!=='undefined'){
  const boot=()=>{try{mountOneHostMenu();}catch(error){console.warn('NOX MENU HOLD',error.message);}};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
}


export function installShellKeys(doc=document){
  doc.addEventListener('keydown', (event) => {
    if (event.key === 'F11') {
      event.preventDefault();
      const el = doc.documentElement;
      if (!doc.fullscreenElement) el.requestFullscreen?.();
      else doc.exitFullscreen?.();
    }
    if (event.key === 'Escape' && doc.fullscreenElement) {
      doc.exitFullscreen?.();
    }
  });
}
