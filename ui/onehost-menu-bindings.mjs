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
        !(Object.keys(payload).length===0 ||
          (Object.keys(payload).length===1 && typeof payload.enabled==='boolean')))
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
// Native COMPLETED is a transport state, never a privileged owner ACK.
// Deny embedded provider/consent errors even alongside a positive model tag.
export function nativeOwnerReceiptHolds(owner,depth=0,trail=new Set()) {
  // Native transport COMPLETED is not consent. Nested owner approvals/denials
  // must be read from the SAME bound route before admitting LEARN/SETTINGS.
  if (!owner || typeof owner!=='object' ||
      depth>4 || trail.has(owner)) return true;
  trail.add(owner);
  // Native WPF bounds nested receipt arrays; their hidden owner denials
  // must never become a successful LEARN queue or SETTINGS HKCU readback.
  if (Array.isArray(owner)) {
    if (depth===0 || owner.length>128) return true;
    for (const item of owner) {
      if (item!==null && typeof item==='object' &&
          nativeOwnerReceiptHolds(item,depth+1,trail)) return true;
    }
    trail.delete(owner);
    return false;
  }
  if (Object.prototype.hasOwnProperty.call(owner,'ok') &&
      typeof owner.ok!=='boolean') return true;
  if (owner.ok===false || owner.ack===false ||
      (Object.prototype.hasOwnProperty.call(owner,'ack') &&
       typeof owner.ack!=='boolean')) return true;
  // A false native permission or operation bit is an actual owner denial,
  // even if a surrounding IPC envelope advertises COMPLETED.
  // An explicitly negative native grant is an owner refusal, even if the
  // transport says COMPLETED and HKCU enabled/readOnly otherwise look valid.
  // Absent optional grant fields remain backward-compatible with original WPF.
  for (const key of ['success','approved','authorized',
    'consented','ownerConsent','nativeConsent','permissionGranted']) {
    if (Object.prototype.hasOwnProperty.call(owner,key) && owner[key]!==true)
      return true;
  }
  if (Object.prototype.hasOwnProperty.call(owner,'errorCode') &&
      owner.errorCode!=null && String(owner.errorCode).trim()!=='') return true;
  // Native owner/provider failures may use snake_case or an error field.
  // A COMPLETED transport carrying either is never an accepted owner result.
  // Native errorMessage/error_message are error envelopes too, never owner consent.
  for (const key of ['error','error_code','errorMessage','error_message']) {
    if (Object.prototype.hasOwnProperty.call(owner,key) && owner[key]!=null &&
        (typeof owner[key]!=='string' || owner[key].trim()!=='')) return true;
  }
  const blocked=new Set(['HOLD','OFFLINE','ERROR','ERRORS','FAILED','DENIED',
    'REJECTED','CANCELLED','CANCELED','UNAVAILABLE','BLOCKED','UNAUTHORIZED',
    'FORBIDDEN','ABORTED','REVOKED','EXPIRED','STOPPING','REFUSED']);
  const pairs=new Set(['NOT_READY','AUTH_REQUIRED','NEEDS_AUTH','CONSENT_REQUIRED',
    'TIMED_OUT','STOP_REQUESTED','PERMISSION_REQUIRED','AUTHORIZATION_REQUIRED',
    'NOT_AUTHORIZED','NOT_AUTHENTICATED','AWAITING_CONSENT','NEEDS_CONSENT',
    'CONSENT_PENDING','SID_MISMATCH','ACL_MISMATCH']);
  for (const key of ['status','state']) {
    const value=owner[key];
    if(value==null)continue;
    if(typeof value!=='string')return true;
    const words=value.trim().toUpperCase().match(/[A-Z0-9]+/g)||[];
    if(words.some(word=>blocked.has(word)))return true;
    if(words.length>1 && ['REQUIRED','MISMATCH'].includes(words.at(-1)))return true;
    for(let i=0;i+1<words.length;i++)
      if(pairs.has(words[i]+'_'+words[i+1]))return true;
  }
  // Preserve data arrays as data; recursively examine only actual nested
  // owner/receipt envelopes. Cyclic or excessively deep replies HOLD.
  for (const key of ['ownerResult','nativeResult','owner','receipt','result']) {
    if (!Object.prototype.hasOwnProperty.call(owner,key)) continue;
    const child=owner[key];
    if (child===null || child===undefined) continue;
    if (typeof child==='object') {
      if (nativeOwnerReceiptHolds(child,depth+1,trail)) return true;
    } else if (key!=='result') return true;
  }
  trail.delete(owner);
  return false;
}

export function nativeCompletedOwnerReply(reply) {
  // Transport COMPLETED does not certify native OWNER/CONSENT/provider success.
  // Never turn an envelope error or embedded HOLD into buttons, model ACK or AI PASS.
  return reply?.state==='COMPLETED' &&
    !nativeOwnerReceiptHolds(reply) &&
    !nativeOwnerReceiptHolds(reply.result);
}

// A COMPLETED transport is not a real functional result without a matching route.
export function nativeReadVerified(reply,route){
  return reply?.routeId===route&&nativeCompletedOwnerReply(reply)&&
    reply.result!==null&&typeof reply.result==='object'&&!Array.isArray(reply.result);
}

// Native owner HKCU readback must match the requested SETTINGS Boolean.
// COMPLETED is never evidence of persisted configuration by itself.
export function nativeAutostartPersistenceAck(reply,requested){
  if(!nativeReadVerified(reply,'system.autostart') ||
     typeof reply.result.enabled!=='boolean')return false;
  // Only the original WPF {enabled,readOnly} receipt proves an HKCU result.
  // Nested progress/status, even under transport COMPLETED, is not persisted
  // Windows state and must never be displayed as SETTINGS success.
  if(Object.prototype.hasOwnProperty.call(reply.result,'status') ||
     Object.prototype.hasOwnProperty.call(reply.result,'state'))return false;
  // A new process can inspect HKCU via the original owner without mutating it.
  // Read-only state is never evidence that an ON/OFF write succeeded.
  if(requested===null)return reply.result.readOnly===true;
  return typeof requested==='boolean' && reply.result.readOnly===false &&
    reply.result.enabled===requested;
}

// Stable WebView2 UIA IDs are owner-bound to the original SETTINGS buttons,
// not just matching renderer text/data. The native WPF consent check still applies.
export const AUTOSTART_UIA_IDS=Object.freeze({
  read:'nox-express-settings-autostart-read',
  on:'nox-express-settings-autostart-on',
  off:'nox-express-settings-autostart-off'
});
export function settingsAutostartOwnerAdmission(button,issued){
  const id=button?.id;
  const expected=id===AUTOSTART_UIA_IDS.read?{key:'',value:''}:
    id===AUTOSTART_UIA_IDS.on?{key:'enabled',value:'true'}:
    id===AUTOSTART_UIA_IDS.off?{key:'enabled',value:'false'}:null;
  if(!expected || !issued?.has?.(button) || button.isConnected!==true ||
     button.tagName!=='BUTTON' || button.dataset?.nativeRoute!=='system.autostart' ||
     button.dataset.nativeKey!==expected.key || button.dataset.nativeValue!==expected.value)
    return false;
  // A duplicate, replaced or detached UIA node must not dispatch owner IPC.
  const matches=button.ownerDocument?.querySelectorAll?.('[id="'+id+'"]');
  if(matches?.length!==1 || matches[0]!==button)return false;
  // An authentic but hidden, inert or occluded UIA node is not an owner gesture.
  // Native WPF independently checks Windows SID, route ACL and user consent.
  try{
    const doc=button.ownerDocument,view=doc?.defaultView;
    if(typeof view?.getComputedStyle!=='function' ||
       typeof doc?.elementFromPoint!=='function' ||
       typeof button.getBoundingClientRect!=='function')return false;
    const rect=button.getBoundingClientRect();
    if(!rect || ![rect.left,rect.right,rect.top,rect.bottom,
                  view.innerWidth,view.innerHeight].every(Number.isFinite) ||
       rect.right<=rect.left || rect.bottom<=rect.top)return false;
    const x=(rect.left+rect.right)/2,y=(rect.top+rect.bottom)/2;
    if(x<0 || y<0 || x>=view.innerWidth || y>=view.innerHeight)return false;
    let node=button,depth=0;
    while(node){
      if(++depth>64 || node.hidden===true || node.inert===true ||
         node.disabled===true || node.getAttribute?.('aria-hidden')==='true' ||
         node.getAttribute?.('aria-disabled')==='true')return false;
      const style=view.getComputedStyle(node);
      if(!style || style.display==='none' ||
         style.visibility==='hidden' || style.visibility==='collapse' ||
         style.pointerEvents==='none' ||
         !Number.isFinite(Number(style.opacity)) ||
         Number(style.opacity)<=0)return false;
      node=node.parentElement;
    }
    const hit=doc.elementFromPoint(x,y);
    return hit===button || button.contains?.(hit)===true;
  }catch(_){return false;}
}

/** SETTINGS owner requests are single-flight: a second ON/OFF/read cannot race
 * an unconfirmed native HKCU write and misreport persisted state.
 * WPF still owns all SID/ACL/consent and Windows Registry decisions. */
export function createAutostartOwnerFlow(nativeRequest){
  if(typeof nativeRequest!=='function')throw Error('NOX_AUTOSTART_NATIVE_OWNER_REQUIRED');
  let inFlight=false;
  return Object.freeze({
    async request(payload){
      if(inFlight)throw Error('NOX_AUTOSTART_OWNER_IN_FLIGHT');
      inFlight=true;
      try{
        const keys=payload&&typeof payload==='object'&&!Array.isArray(payload)?
          Object.keys(payload):[];
        if(!(keys.length===0 ||
          (keys.length===1&&keys[0]==='enabled'&&typeof payload.enabled==='boolean')))
          throw Error('NOX_AUTOSTART_BOOLEAN_REQUIRED');
        const write=keys.length===1;
        const reply=await nativeRequest('system.autostart',payload);
        if(!write){
          // A native read must independently attest HKCU state. Never return
          // a transport/progress or write-shaped receipt as verified SETTINGS.
          if(!nativeAutostartPersistenceAck(reply,null))
            throw Error('NOX_AUTOSTART_READ_UNVERIFIED');
          return reply;
        }
        // Transport COMPLETED is not an independent Windows Registry readback.
        // Keep the existing WPF owner's SETTINGS lock through a fresh read-only
        // native route invocation; denied, stale, or mismatched results fail closed.
        if(!nativeAutostartPersistenceAck(reply,payload.enabled))
          throw Error('NOX_AUTOSTART_WRITE_UNVERIFIED');
        const readback=await nativeRequest('system.autostart',{});
        if(!nativeAutostartPersistenceAck(readback,null) ||
          readback.result.enabled!==payload.enabled)
          throw Error('NOX_AUTOSTART_READBACK_HOLD');
        return reply;
      }
      finally{inFlight=false;}
    }
  });
}

const OWNER_S03_READ_ACTIONS=new Set([
  'selfbuilder.capabilities','selfbuilder.worker.status','selfbuilder.study.queue',
  'selfbuilder.learning.proofs','selfbuilder.sources.inspect','selfbuilder.coding.models'
]);
// A verified S03 READ is not an owner ACK, job acceptance or trained weight.
export function nativeVerifiedReadAction(reply,action){
  if(!OWNER_S03_READ_ACTIONS.has(action)||!nativeReadVerified(reply,'chat.commands'))
    return {readVerified:false,errorCode:'S03_NATIVE_READ_OWNER_HOLD'};
  const data=reply.result;
  const record=x=>x!==null&&typeof x==='object'&&!Array.isArray(x);
  let good=false;
  switch(action){
    case 'selfbuilder.capabilities':
      good=data.status==='SOURCE_SERVICE'&&record(data.actions)&&data.weights_updated===false;break;
    case 'selfbuilder.worker.status':
      good=['READY_FOR_OWNER_TASK','STOPPED'].includes(data.status)&&
        Array.isArray(data.tasks)&&data.weights_updated===false;break;
    case 'selfbuilder.study.queue':
    case 'selfbuilder.learning.proofs':
      good=data.status==='S03_READ'&&Array.isArray(data.tasks)&&data.weights_updated===false;break;
    case 'selfbuilder.sources.inspect':
      good=data.status==='SOURCE_INVENTORY_READ_ONLY'&&Array.isArray(data.items)&&
        Number.isInteger(data.owner_admitted_total);break;
    case 'selfbuilder.coding.models':
      good=data.status==='DISCOVERY_RESPONDED'&&Array.isArray(data.models)&&
        data.download_performed===false;break;
  }
  if(!good)return {readVerified:false,errorCode:'S03_READ_RECEIPT_SHAPE_HOLD'};
  // May contain queued/HOLD task results. No implied training or mutation.
  return {...data,readVerified:true};
}

export function nativeOwnerActionReceipt(reply,route,action,expectedJobId=null) {
  const owner=reply?.result;
  if(reply?.routeId!==route || !nativeCompletedOwnerReply(reply) ||
     !owner || typeof owner!=='object' || Array.isArray(owner) ||
     owner.ack!==true)
    return {ack:false,errorCode:reply?.errorCode||owner?.errorCode||'NATIVE_ACK_UNCONFIRMED'};
  if(action==='selfbuilder.propose' &&
     (typeof owner.run_id!=='string'||!/^S03-[A-Za-z0-9._:-]{1,128}$/.test(owner.run_id) ||
      typeof owner.source_head!=='string'||!/^[a-f0-9]{40}(?:[a-f0-9]{24})?$/.test(owner.source_head)))
    return {ack:false,errorCode:'S03_PROPOSAL_RECEIPT_UNVERIFIED'};
  // Training ACK is only an exact, durable SQLite S03 QUEUE claim. It must
  // never be accepted as execution, completed training, or updated weights.
  if(action==='selfbuilder.train.request'){
    const queued=route==='training.start' &&
      typeof expectedJobId==='string' &&
      /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(expectedJobId) &&
      owner.job_id===expectedJobId && owner.status==='QUEUED' &&
      Number.isSafeInteger(owner.task_id) && owner.task_id>0 &&
      owner.durable_s03===true && owner.execution_completed===false &&
      owner.training_completed===false && owner.weights_updated===false &&
      owner.activation_allowed===false;
    if(!queued)return {ack:false,errorCode:'TRAINING_S03_QUEUE_RECEIPT_HOLD'};
    return {...owner,ack:true,queueVerified:true};
  }
  return {...owner,ack:true};
}

// Bind a model-cancel ACK to the exact owner-approved job, not just the
// native transport state. STOP_REQUESTED is a request receipt, not termination.
export function nativeModelCancelAck(reply,jobId) {
  if(typeof jobId!=='string'||!jobId||reply?.routeId!=='models.cancel')return false;
  const owner=reply.result;
  if(!owner||typeof owner!=='object'||Array.isArray(owner)||owner.jobId!==jobId)return false;
  if(reply.state==='COMPLETED') {
    if(owner.cancelled!==true)return false;
    // A confirmed cancellation is successful for THIS job. The generic
    // nativeOwnerReceiptHolds() correctly rejects CANCELLED for other actions,
    // but would mislabel the terminal P03 cancel acknowledgement as HOLD.
    // Strip only the two exact terminal spellings on the isolated cancel
    // receipt; keep ACL, consent, errorCode, ack and all other denials intact.
    const terminal={...owner};
    for(const key of ['status','state']) {
      if(typeof terminal[key]==='string'&&
         ['CANCELLED','CANCELED'].includes(terminal[key].trim().toUpperCase()))
        delete terminal[key];
    }
    return nativeCompletedOwnerReply({...reply,result:terminal});
  }
  // A STOP_REQUESTED transport envelope is not proof of a native P03 owner
  // effect. The original Windows OneHost owner emits this state only after
  // an exact job's native result attests cancelled:true. Require that same
  // positive bit here, without equating a request with terminated weights.
  if(reply.state!=='STOP_REQUESTED'||owner.cancelled!==true)return false;
  // This is only a transport request ACK. Reject any outer consent/provider
  // denial, including native snake_case/non-string error fields.
  const envelope={...reply};
  delete envelope.state; // only the exact STOP_REQUESTED transport state
  if(envelope.status==='STOP_REQUESTED')delete envelope.status;
  if(nativeOwnerReceiptHolds(envelope))return false;
  // Only the exact STOP-request state is admissible; nested denial still HOLD.
  const receipt={...owner};
  if(receipt.status==='STOP_REQUESTED')delete receipt.status;
  if(receipt.state==='STOP_REQUESTED')delete receipt.state;
  return !nativeOwnerReceiptHolds(receipt);
}

export function isNativeChatTerminal(reply){
  // Called only AFTER createNativeMenuClient validates a UA-trusted WebView2
  // response with the matching request nonce and exact route. A real native
  // HOLD closes the pending request irrespective of its specific errorCode;
  // STOP_REQUESTED and partial completion must never unlock concurrent chat.
  return reply?.routeId==='helion.chat' &&
    (reply.state==='HOLD'||reply.state==='COMPLETED'&&reply.result?.done===true);
}
// Exact native owner acknowledgement, not a UI value or transport completion.
export function nativeModelSelectionAck(reply,requested){
  return typeof requested==='string'&&requested.length>0&&
    reply?.routeId==='chat.model'&&nativeCompletedOwnerReply(reply)&&
    reply.result?.selectedModel===requested;
}
export function nativeModelReady(model,confirmed,pending){
  return typeof model==='string'&&model.length>0&&model===confirmed&&pending===false;
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
  const autostartFlow=createAutostartOwnerFlow((route,payload)=>client.request(route,payload));
  let states=Object.create(null),trainingJobs=[],disposed=false,menu=null;
  let selectionEpoch=0,capabilityEpoch=0,historyEpoch=0,chatBusy=false,stopRequestPending=false;
  let modelConfirmed='',modelSelectionPending=false;
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
  const issuedSettingsControls=new WeakSet();
  const appendSystemAutostartButtons=()=>{
    for(const button of actions.querySelectorAll?.('[data-native-route="system.autostart"]')||[])button.remove();
    const currentWorld=doc.getElementById('detail-title')?.textContent||'';
    if(!/(?:system|систем)/i.test(currentWorld))return;
    // Explicit owner-only registry read, including after a fresh app launch.
    // It asks for native WPF consent; it never writes HKCU or grants privileges.
    const read=doc.createElement('button');read.type='button';read.className='nox-sb-tile';
    read.textContent='Проверить автозапуск NOX · Windows';read.id=AUTOSTART_UIA_IDS.read;
    read.dataset.nativeRoute='system.autostart';read.dataset.nativeKey='';read.dataset.nativeValue='';
    issuedSettingsControls.add(read);actions.append(read);
    for(const [label,value] of [['Автозапуск NOX · ВКЛ','true'],['Автозапуск NOX · ВЫКЛ','false']]){
      const button=doc.createElement('button');button.type='button';button.className='nox-sb-tile';
      button.textContent=label;button.id=value==='true'?AUTOSTART_UIA_IDS.on:AUTOSTART_UIA_IDS.off;
      button.dataset.nativeRoute='system.autostart';
      button.dataset.nativeKey='enabled';button.dataset.nativeValue=value;
      issuedSettingsControls.add(button);actions.append(button);
    }
  };
  // Actual existing OneHost/P02 read handlers. No model pull, training,
  // PC control, fake result or second host can originate from these probes.
  const verifiedReadPanels=Object.freeze({
    'РАБОТА':[['Задания','chat.commands','action','selfbuilder.worker.status']],
    'ИНТЕЛЛЕКТ':[['Каталог моделей','models.catalog','',''],['Активатор','chat.commands','action','selfbuilder.activator.status']],
    'ЗНАНИЯ':[['История','chat.history','',''],['Исходники','chat.commands','action','selfbuilder.sources.inspect']],
    'РАЗВИТИЕ':[['Очередь обучения','chat.commands','action','selfbuilder.study.queue'],['Доказательства обучения','chat.commands','action','selfbuilder.learning.proofs'],['GPU preflight','gpu.preflight','','']],
    'СИСТЕМА':[['Очередь моделей','models.queue','',''],['Каталог моделей','models.catalog','',''],['GPU preflight','gpu.preflight','',''],['Активатор','chat.commands','action','selfbuilder.a1.status']]
  });
  const appendFunctionalReadButtons=()=>{
    for(const prior of actions.querySelectorAll?.('[data-nox-functional-read]')||[])prior.remove();
    const section=(doc.getElementById('detail-title')?.textContent||'').trim();
    for(const [label,route,key,value] of verifiedReadPanels[section]||[]){
      const b=doc.createElement('button');b.type='button';b.className='nox-sb-tile';
      b.textContent=label;b.dataset.noxFunctionalRead='1';
      b.dataset.nativeRoute=route;b.dataset.nativeKey=key;b.dataset.nativeValue=value;
      actions.append(b);
    }
  };
  const display=(v,expectedRoute,expectedAutostart=null)=>{
    if(disposed)return;
    const approved=expectedRoute==='system.autostart'
      ? nativeAutostartPersistenceAck(v,expectedAutostart)
      : nativeReadVerified(v,expectedRoute);
    const data=approved?v.result:null;actions.replaceChildren();
    function action(label,route,key,id){
      const b=doc.createElement('button');b.type='button';b.className='nox-sb-tile';b.textContent=label;
      b.dataset.nativeRoute=route;b.dataset.nativeKey=key;b.dataset.nativeValue=id;actions.append(b);
    }
    if(approved&&Array.isArray(data?.models))for(const model of data.models){
      if(model?.downloadEligible!==true||!Array.isArray(model.artifacts))continue;
      for(const artifact of model.artifacts){
        if(typeof artifact?.tag!=='string'||!artifact.tag)continue;
        action('Скачать · '+artifact.tag,'models.pull','modelTag',artifact.tag);
        action('Импортировать GGUF · '+artifact.tag,'models.gguf.import','modelTag',artifact.tag);
      }
    }
    if(approved&&Array.isArray(data?.jobs))for(const job of data.jobs){
      if(typeof job?.id!=='string')continue;
      if(['queued','running','downloading'].includes(String(job.state).toLowerCase()))action('Отменить · '+job.id,'models.cancel','jobId',job.id);
      if(['failed','cancelled','canceled'].includes(String(job.state).toLowerCase()))action('Повторить · '+job.id,'models.retry','jobId',job.id);
    }
    if(approved&&data?.schema==='NOX-ACTIVATOR-WORM-STATUS-v1'){
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
    if(approved&&v.routeId?.startsWith('models.'))action('Обновить очередь загрузки','models.queue','','');
    appendSystemAutostartButtons();
    appendActivatorShortcut();
    appendFunctionalReadButtons();
    detail.hidden=!data;detail.textContent=data?JSON.stringify(data,null,2):'';
    status.textContent=expectedRoute==='system.autostart'
      ? approved
        ? expectedAutostart===null
          ? 'Состояние автозапуска NOX · '+(data.enabled?'ВКЛ':'ВЫКЛ')+' · HKCU прочитан'
          : 'Автозапуск NOX · '+(expectedAutostart?'ВКЛ':'ВЫКЛ')+' · Windows подтверждено'
        : 'HOLD · '+(v?.errorCode||v?.result?.errorCode||'NOX_AUTOSTART_PERSISTENCE_UNVERIFIED')
      : (v.state==='HOLD'||v.state==='COMPLETED'&&!approved)?'HOLD · '+(v.errorCode||data?.errorCode||'NATIVE_OWNER_UNCONFIRMED'):
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
        if(!disposed&&doc.getElementById('detail-title')?.textContent?.trim()==='РАЗВИТИЕ')display(reply,'models.queue');
        return nativeReadVerified(reply,'models.queue')&&Array.isArray(reply.result?.jobs)
          ? {ack:true,jobs:reply.result.jobs}
          : {ack:false,errorCode:reply.errorCode||'P03_QUEUE_UNAVAILABLE'};
      },
      invokeP03Cancel:async jobId=>{
        const reply=await client.request('models.cancel',{jobId});
        // Native ACK confirms STOP request acceptance, not job termination.
        return nativeModelCancelAck(reply,jobId)
          ? {ack:true,state:'STOP_REQUESTED'}
          : {ack:false,errorCode:reply.errorCode||'P03_STOP_UNVERIFIED'};
      },
      invokeNative:async request=>{
        root.append(status,detail,actions);detail.hidden=true;
        const scope=context();
        if(!scope.core_id||!scope.persona_id)throw Error('SELECT_CORE_AND_PERSONA');
        const route=request.actionId==='selfbuilder.train.request'?'training.start':'chat.commands';
        const result=await client.request(route,{...(route==='chat.commands'?{action:request.actionId}:{}),...scope,
          ...(request.task?{task:request.task}:{}),...(request.job_id?{job_id:request.job_id}:{})});display(result,route);
        return OWNER_S03_READ_ACTIONS.has(request.actionId)
          ? nativeVerifiedReadAction(result,request.actionId)
          : nativeOwnerActionReceipt(result,route,request.actionId,request.job_id);
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
  const sectionObserver=root&&view.MutationObserver?new view.MutationObserver(()=>{menu?.refresh();appendSystemAutostartButtons();appendActivatorShortcut();appendFunctionalReadButtons();}):null;
  const title=doc.getElementById('detail-title');
  if(title)sectionObserver?.observe(title,{childList:true,characterData:true,subtree:true});
  // One passive local probe on first MENU mount. No download, training or patch.
  if(root)void client.request('chat.commands',{action:'selfbuilder.activator.status'})
    .then(reply=>{if(!disposed&&activatorSection())display(reply,'chat.commands');})
    .catch(()=>{if(!disposed&&activatorSection())status.textContent='ACTIVATOR HOLD · локальная проверка недоступна';});
  async function refresh(){
    const epoch=selectionEpoch,run=++capabilityEpoch,scope=context();
    try{
      if(!scope.core_id||!scope.persona_id)throw Error('SELECT_CORE_AND_PERSONA');
      const reply=await client.request('chat.commands',{action:'selfbuilder.capabilities',...scope});
      if(run!==capabilityEpoch||!sameSelection(epoch,scope))return;
      states=Object.create(null);trainingJobs=[];
      if(nativeReadVerified(reply,'chat.commands')&&Array.isArray(reply.result?.trainingJobs))trainingJobs=reply.result.trainingJobs.filter(x=>typeof x?.id==='string');
      if(nativeReadVerified(reply,'chat.commands') && reply.result?.actions && typeof reply.result.actions==='object')
        for(const action of ACTIONS){
          const s=reply.result.actions[action];
          if(s&&typeof s==='object')states[action]={available:s.available===true,
            status:typeof s.status==='string'?s.status:'HOLD',ownerConsent:s.ownerConsent===true,requiresNativeConsent:s.requiresNativeConsent===true};
        }
      menu?.refresh();display(reply,'chat.commands');
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
      if(nativeOwnerActionReceipt(reply,'chat.commands',action).ack!==true)throw Error('R5_NATIVE_HOLD');
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
  // FAST02 NEURAL FLOW: this original chat accent follows ONLY verified
  // OneHost stream deltas and pending/native end states. No fake training.
  const chatScene=doc.getElementById('chat');
  const chatLog=doc.getElementById('chat-log');
  let neuralFlow=null;
  if(chatScene&&chatLog&&chatScene.contains(chatLog)&&
     typeof doc.createElementNS==='function'&&
     !chatScene.querySelector?.('.nox-native-flow')){
    neuralFlow=doc.createElement('div');
    neuralFlow.className='nox-native-flow';
    neuralFlow.setAttribute('aria-hidden','true');
    const ns='http://www.w3.org/2000/svg';
    const mesh=doc.createElementNS(ns,'svg');
    mesh.setAttribute('viewBox','0 0 320 32');
    mesh.setAttribute('aria-hidden','true');
    for(let i=0;i<18;i++){
      const node=doc.createElementNS(ns,'circle');
      const x=8+i*18,y=16+Math.sin(i*.85)*9;
      node.setAttribute('cx',String(x));node.setAttribute('cy',String(y));
      node.setAttribute('r',i%3===0?'1.8':'1.2');
      mesh.append(node);
      if(i>0){
        const line=doc.createElementNS(ns,'line');
        line.setAttribute('x1',String(x-18));
        line.setAttribute('y1',String(16+Math.sin((i-1)*.85)*9));
        line.setAttribute('x2',String(x));line.setAttribute('y2',String(y));
        mesh.append(line);
      }
    }
    neuralFlow.append(mesh);
    chatLog.before(neuralFlow);
    chatScene.dataset.noxNeuralFlow='IDLE';
  }
  const setNeuralFlow=state=>{
    if(neuralFlow&&!disposed&&['IDLE','REQUESTED','STREAMING','COMPLETED','STOP_REQUESTED','HOLD'].includes(state))
      chatScene.dataset.noxNeuralFlow=state;
  };
  async function sendChat(){
    const scope=context(),text=value('chat-input').trim(),model=value('chat-model'),epoch=selectionEpoch;
    if(!scope.core_id||!scope.persona_id||!text||!nativeModelReady(model,modelConfirmed,modelSelectionPending)){
      chatStatus('HOLD · OneHost не подтвердил выбранную локальную модель');return;
    }
    if(chatBusy)return;chatBusy=true;setNeuralFlow('REQUESTED');
    const send=doc.getElementById('chat-send'),stop=doc.getElementById('chat-stop');
    const visible=()=>sameSelection(epoch,scope,model);
    // A native terminal envelope is not proof of an AI answer. Only actual
    // owner text or a nonempty trusted native STREAMING delta may complete UI.
    let receivedNonemptyStream=false;
    const verifiedNativeText=reply=>receivedNonemptyStream ||
      (typeof reply?.result?.answer==='string'&&reply.result.answer.trim().length>0);
    const release=reply=>{
      if(!chatTerminal(reply))return;
      chatBusy=false;
      if(visible())setNeuralFlow(nativeCompletedOwnerReply(reply)&&verifiedNativeText(reply)?'COMPLETED':'HOLD');
      if(!disposed){
        if(send)send.disabled=chatBusy||!nativeModelReady(value('chat-model'),modelConfirmed,modelSelectionPending);
        if(stop)stop.disabled=false;
        if(visible()&&nativeCompletedOwnerReply(reply)){
          if(typeof reply.result?.answer==='string'&&reply.result.answer.trim())
            row.textContent=reply.result.answer;
          chatStatus(verifiedNativeText(reply)?'COMPLETED · локальная модель':
            'HOLD · пустой ответ локальной модели');
        }
      }
    };
    if(send)send.disabled=true;if(stop)stop.disabled=false;
    const row=doc.createElement('p');row.dataset.noxNativeChat='answer';
    doc.getElementById('chat-log')?.append(row);if(visible())chatStatus('REQUESTED · локальное ядро');
    try{
      const reply=await client.request('helion.chat',{text,model,...scope},event=>{
        if(typeof event?.delta==='string'&&event.delta.trim()){
          receivedNonemptyStream=true;
          if(visible())setNeuralFlow('STREAMING');
        }
        if(visible()&&row.isConnected){row.textContent+=event.delta;chatStatus('STREAMING · локальная модель');}
      },release);
      if(disposed)return;
      release(reply);
      if(visible()){
        if(nativeCompletedOwnerReply(reply)&&typeof reply.result?.answer==='string'&&reply.result.answer.trim())
          row.textContent=reply.result.answer;
        chatStatus(!nativeCompletedOwnerReply(reply)?'HOLD · '+(reply.errorCode||reply.result?.errorCode||'NO_MODEL_REPLY'):
          reply.result?.done===true?(verifiedNativeText(reply)?'COMPLETED · локальная модель':
            'HOLD · пустой ответ локальной модели'):'HOLD · ответ не завершён');
      }
    }catch(error){
      if(['NOX_NATIVE_REQUEST_DENIED','NOX_NATIVE_CLIENT_DISPOSED','NOX_NATIVE_REQUEST_LIMIT',
        'NOX_NATIVE_NONCE_COLLISION','NOX_NATIVE_POST_FAILED'].includes(error.message))chatBusy=false;
      if(visible()){
        setNeuralFlow('HOLD');
        chatStatus(error.message==='TIMEOUT'?'HOLD · native не завершён, STOP доступен':'HOLD · соединение с ядром');
      }
    }finally{if(!disposed){if(send)send.disabled=chatBusy||!nativeModelReady(value('chat-model'),modelConfirmed,modelSelectionPending);if(stop)stop.disabled=false;}}
  }
  async function models(){
    const select=doc.getElementById('chat-model');if(!select)return;
    const observedEpoch=selectionEpoch;
    try{
      const reply=await client.request('chat.model',{});
      if(disposed||observedEpoch!==selectionEpoch||modelSelectionPending||
         !nativeReadVerified(reply,'chat.model')||!Array.isArray(reply.result?.models))return;
      select.replaceChildren();
      const names=[...new Set(reply.result.models.filter(name=>
        typeof name==='string'&&name.length>0&&name.length<=160))].slice(0,64);
      for(const name of names){const option=doc.createElement('option');option.value=name;option.textContent=name;select.append(option);}
      const selected=reply.result.selectedModel;
      modelConfirmed=names.includes(selected)&&nativeModelSelectionAck(reply,selected)?selected:'';
      select.value=modelConfirmed;
      const send=doc.getElementById('chat-send');
      if(send)send.disabled=!nativeModelReady(select.value,modelConfirmed,modelSelectionPending);
      chatStatus(modelConfirmed?'LOCAL · модель подтверждена OneHost':'HOLD · локальная модель не подтверждена');
    }catch(_){modelConfirmed='';const send=doc.getElementById('chat-send');if(send)send.disabled=true;chatStatus('HOLD · модель не обнаружена');}
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
    if(generated&&route==='system.autostart' &&
       !settingsAutostartOwnerAdmission(button,issuedSettingsControls)){
      event.preventDefault();event.stopImmediatePropagation();
      status.textContent='HOLD · NOX_AUTOSTART_UIA_OWNER_IDENTITY';return;
    }
    event.preventDefault();event.stopImmediatePropagation();
    button.closest('section')?.append(status,detail,actions);detail.hidden=true;
    if(button.id==='chat-stop'&&stopRequestPending)return;
    if(button.id==='chat-stop'){stopRequestPending=true;setNeuralFlow('STOP_REQUESTED');}
    button.disabled=true;status.textContent='REQUESTED · ожидается ответ ядра';
    const task='Сверь существующие D02/HOME/MENU10/WOW и журнал ошибок с текущим SourceLock. Создай ОДИН безопасный дополнительный исходный патч для живой кнопки, раздела или графического эффекта: точный путь, рабочий обработчик, разрешения, STOP, регрессионный тест, SHA и откат. Сохрани исходные 8 астероидов, 10 миров, personas, WebView2, S03/P03, без изменения EXE без независимой приёмки.';
    if(generated&&route==='chat.history'){
      const scope=context();
      if(!scope.core_id||!scope.persona_id){
        status.textContent='HOLD · выберите CoreID и Persona для истории';button.disabled=false;return;
      }
    }
    const payload=generated&&route==='chat.history'?{limit:50,...context()}
      :generated&&route==='system.autostart'
      ?(button.dataset.nativeKey==='enabled'?{enabled:button.dataset.nativeValue==='true'}:{})
      :generated&&route==='chat.commands'&&button.dataset.nativeValue==='selfbuilder.propose'
      ?{action:'selfbuilder.propose',task}
      :generated&&route==='chat.commands'&&button.dataset.nativeKey==='action'
      ?{action:button.dataset.nativeValue,...context()}
      :generated?(button.dataset.nativeKey?{[button.dataset.nativeKey]:button.dataset.nativeValue}:{})
      :route==='chat.commands'?{action:'selfbuilder.worker.status',...context()}:{};
    const visibleSection=doc.getElementById('detail-title')?.textContent;
    try{
      const reply=route==='system.autostart'
        ? await autostartFlow.request(payload) : await client.request(route,payload);
      if(!disposed&&button.isConnected&&doc.getElementById('detail-title')?.textContent===visibleSection)
        display(reply,route,route==='system.autostart'?payload.enabled:null);
    }catch(error){
      if(!disposed&&button.isConnected&&doc.getElementById('detail-title')?.textContent===visibleSection)
        status.textContent=(error.message==='TIMEOUT'?'TIMEOUT':'HOLD')+' · запрос не подтверждён';
    }
    finally{if(button.id==='chat-stop')stopRequestPending=false;if(!disposed)button.disabled=false;}
  }
  async function change(event){
    if(!['chat-core','chat-persona','chat-model','chat-provider'].includes(event.target?.id))return;
    ++selectionEpoch;setNeuralFlow('IDLE');const historyRun=++historyEpoch,epoch=selectionEpoch;
    // Changing model, core, persona or provider invalidates the prior ACK.
    modelConfirmed='';
    if(value('chat-provider')==='OPENAI')return;
    const scope=context(),send=doc.getElementById('chat-send');
    if(send)send.disabled=true;
    if(!scope.core_id||!scope.persona_id)return;
    event.stopImmediatePropagation();
    try{
      if(event.target.id==='chat-model'){
        if(modelSelectionPending){chatStatus('HOLD · выбор модели уже выполняется');return;}
        const requested=value('chat-model');
        if(!requested){chatStatus('HOLD · укажите модель');return;}
        const select=doc.getElementById('chat-model');
        modelSelectionPending=true;
        if(select)select.disabled=true;
        let chosen;
        try{chosen=await client.request('chat.model',{model:requested,...scope});}
        finally{
          modelSelectionPending=false;
          if(!disposed&&select)select.disabled=false;
        }
        if(historyRun!==historyEpoch||!sameSelection(epoch,scope,requested))return;
        if(!nativeModelSelectionAck(chosen,requested)){
          chatStatus('HOLD · OneHost не подтвердил выбранную модель');return;
        }
        modelConfirmed=requested;
        if(send)send.disabled=chatBusy||!nativeModelReady(value('chat-model'),modelConfirmed,modelSelectionPending);
      }
      const reply=await client.request('chat.history',{limit:100,...scope});
      if(historyRun!==historyEpoch||!sameSelection(epoch,scope))return;
      if(!nativeReadVerified(reply,'chat.history')||!Array.isArray(reply.result?.messages)){chatStatus('HOLD · история недоступна');return;}
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
    view.removeEventListener('pagehide',close);sectionObserver?.disconnect();r11?.destroy();menu?.destroy();wow?.destroy();wowObserver?.disconnect();status.remove();detail.remove();actions.remove();neuralFlow?.remove();if(chatScene?.dataset)delete chatScene.dataset.noxNeuralFlow;client.destroy();
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
