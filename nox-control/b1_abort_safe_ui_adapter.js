/* NOX B1: opt-in browser DOM adapter for streamed turns.
 * Caller must pass AbortSignal from SSE client into onDelta().
 * UI projection is NOT proof of server ACK, model completion or S03 storage.
 * No network calls, storage writes, or production wiring occur in this module.
 */
(function(root,factory){
  'use strict';
  const api=factory();
  if(typeof module==='object' && module.exports) module.exports=api;
  else root.NOXB1AbortSafeUI=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const ID=/^[A-Za-z0-9._:-]{1,128}$/;
  class UiHold extends Error {
    constructor(code){super(code);this.name='UiHold';this.code=code;}
  }
  const hold=code=>{throw new UiHold(code);};
  function scope(s){
    if(!s||typeof s!=='object'||Array.isArray(s)||
       typeof s.conversation_id!=='string'||!ID.test(s.conversation_id)||
       typeof s.exchange_id!=='string'||!ID.test(s.exchange_id))
      hold('HOLD_B1_UI_SCOPE');
    return {conversation_id:s.conversation_id,exchange_id:s.exchange_id};
  }
  function createUiAdapter({container,beforeCommit=()=>Promise.resolve()}={}){
    if(!container||container.nodeType!==1||
       !container.ownerDocument||
       typeof container.ownerDocument.createElement!=='function'||
       typeof beforeCommit!=='function') hold('HOLD_B1_UI_CONTRACT');
    // Search existing direct children, not only memory, so adapter recreation
    // after reload/reattachment does not duplicate an already-present turn.
    function find(s){
      let found=null;
      for(const el of container.children){
        if(el.dataset.noxB1Conversation===s.conversation_id&&
           el.dataset.noxB1Exchange===s.exchange_id){
          if(found) hold('HOLD_B1_DUPLICATE_DOM_TURN');
          found=el;
        }
      }
      return found;
    }
    function create(s){
      const el=container.ownerDocument.createElement('div');
      el.dataset.noxB1Conversation=s.conversation_id;
      el.dataset.noxB1Exchange=s.exchange_id;
      el.dataset.noxB1State='streaming';
      container.appendChild(el);
      return el;
    }
    async function onDelta(raw,delta,signal){
      const s=scope(raw);
      if(!signal||typeof signal.aborted!=='boolean'||
         typeof signal.addEventListener!=='function'||
         typeof delta!=='string') hold('HOLD_B1_UI_DELTA_CONTRACT');
      if(signal.aborted) return false;
      // Allow deferred layout/render work, but never perform any DOM/state
      // mutation until checking the actual signal AFTER that await.
      await beforeCommit('delta',s);
      if(signal.aborted) return false;
      let el=find(s);
      // A terminal projection is immutable; a late delta cannot reopen it.
      if(el&&el.dataset.noxB1State==='terminal') return false;
      if(!el) el=create(s);
      // textContent, never innerHTML: arbitrary model text cannot inject DOM.
      el.textContent+=delta;
      return true;
    }
    async function upsertTerminal(raw,eventId){
      const s=scope(raw);
      if(typeof eventId!=='string'||!ID.test(eventId))
        hold('HOLD_B1_UI_EVENT_ID');
      await beforeCommit('terminal',s);
      let el=find(s);
      if(el&&el.dataset.noxB1EventId&&el.dataset.noxB1EventId!==eventId)
        hold('HOLD_B1_UI_CONFLICTING_TERMINAL');
      if(!el) el=create(s);
      // Idempotent per exchange, including repeat readback or adapter reset.
      el.dataset.noxB1EventId=eventId;
      el.dataset.noxB1State='terminal';
      return true;
    }
    return Object.freeze({onDelta,upsertTerminal});
  }
  return Object.freeze({createUiAdapter,UiHold});
});
