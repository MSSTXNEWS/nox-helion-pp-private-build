'use strict';
// Additive staging adapter. Original R86/R111 and A6 ZIP remain immutable.
const {createHash}=require('node:crypto');
const fs=require('node:fs');
const R86='bd2e154fd2c6007cb315d310e109de470f54f72f';
const sha=(kind,bytes)=>createHash(kind).update(bytes).digest('hex');
function stageR100(raw){
 if(!Buffer.isBuffer(raw)||sha('sha1',Buffer.concat([Buffer.from('blob '+raw.length+'\0'),raw]))!==R86)throw Error('HOLD_R88_R86_PIN');
 let src=raw.toString('utf8');
 const replace=(before,after)=>{
  if(src.split(before).length!==2)throw Error('HOLD_R88_PATCH_ANCHOR');
  src=src.replace(before,()=>after);
 };
 replace("registerRecheck(()=>{if(row(s,event)!==el||el.textContent!==visible)hold();return true;});",
 "registerRecheck(()=>{if(row(s,event)!==el||el.textContent!==visible)hold();return true;},Object.freeze({bytes,sha256}));");
 replace("let observed=false,recheckPreAck=null;","let observed=false,recheckPreAck=null,retainedObservation=null;");
 replace("observeCtrl.signal,guard=>{","observeCtrl.signal,(guard,observation)=>{");
 replace("recheckPreAck=guard;","recheckPreAck=guard;retainedObservation=observation;");
 replace("if(observePreAck&&observed!==true){discardReadback();hold('HOLD_STREAM_PREACK_OBSERVATION');}",
 `if(observePreAck&&observed!==true){discardReadback();hold('HOLD_STREAM_PREACK_OBSERVATION');}
        // R100: no new ACK from PENDING retention or a local RESERVED grant.
        // An independent host must provide and authenticate both exact receipts.
        if(observePreAck){
          const finalCtrl=new AbortController();
          try{
            await boundedRead(async()=>{
              const recheck=()=>{if(finalCtrl.signal.aborted||signal.aborted)hold('HOLD_STREAM_RECONNECT_STOPPED');assertCurrentPreAck();return true;};
              recheck();
              if(!retainedObservation||typeof host.requestFinalDisposition!=='function'||
                 typeof host.verifyFinalDisposition!=='function')hold('HOLD_R100_PROVIDER');
              const observation=retainedObservation;
              let providerChecked=false;
              const evidence=await host.requestFinalDisposition(Object.freeze({scope:s,observation,grant,
                recheck:()=>{recheck();providerChecked=true;return true;}}),finalCtrl.signal);
              recheck();
              if(!providerChecked||!evidence)hold('HOLD_R100_DISPOSITION');
              const hash=async bytes=>Array.from(new Uint8Array(await globalThis.crypto.subtle.digest('SHA-256',new TextEncoder().encode(bytes))),b=>b.toString(16).padStart(2,'0')).join('');
              const parse=async pair=>{
                if(!Array.isArray(pair)||pair.length!==2||typeof pair[0]!=='string'||typeof pair[1]!=='string'||
                   !/^[0-9a-f]{64}$/.test(pair[1])||pair[0].length>65536)hold('HOLD_R100_DISPOSITION');
                const fixed=Object.freeze([pair[0],pair[1]]);
                if(await hash(fixed[0])!==fixed[1])hold('HOLD_R100_DISPOSITION');
                return {fixed,doc:JSON.parse(fixed[0])};
              };
              const o=await parse([observation.bytes,observation.sha256]);
              const r=await parse(evidence.reservation),d=await parse(evidence.disposition);
              const common=['conversation_id','physical_dialog_id','s03_dialog_id','session_id','served_sha256','server_sha256','owner_admission_receipt_sha256','turn','exchange_id','request_id','attempt_id','event_id','turn_id','user_message_id','assistant_message_id','observation_id','browser_sha256','terminal_receipt_sha256'];
              const exact=(doc,extra)=>doc&&Object.keys(doc).length===common.length+extra.length&&[...common,...extra].every(k=>Object.prototype.hasOwnProperty.call(doc,k));
              const rr=r.doc,dd=d.doc;
              if(!exact(rr,['observation_sha256','schema','reservation_id','state'])||
                 !exact(dd,['observation_sha256','schema','reservation_id','reservation_sha256','disposition_id','state','dom_recheck','stop_recheck'])||
                 common.some(k=>rr[k]!==o.doc[k]||dd[k]!==o.doc[k])||
                 rr.observation_sha256!==o.fixed[1]||dd.observation_sha256!==o.fixed[1]||
                 rr.schema!=='nox.browser.ack-reservation-readback.v1'||rr.state!=='RESERVED_NOT_SENT'||
                 dd.schema!=='nox.browser.projection-disposition.v1'||dd.state!=='FINALIZED'||
                 dd.dom_recheck!=='MATCHED'||dd.stop_recheck!=='CLEAR'||
                 typeof rr.reservation_id!=='string'||!ID.test(rr.reservation_id)||
                 typeof dd.disposition_id!=='string'||!ID.test(dd.disposition_id)||
                 dd.reservation_id!==rr.reservation_id||dd.reservation_sha256!==r.fixed[1]||
                 new Set([o.fixed[1],r.fixed[1],d.fixed[1]]).size!==3)hold('HOLD_R100_DISPOSITION');
              recheck();
              // The provider's returned digest is NOT an independent admission pin.
              // The verifier must independently authenticate both bytes, durable
              // CAS/grant, scope, and final disposition. true is its contract only.
              if(await host.verifyFinalDisposition(Object.freeze({scope:s,grant,observation:o.fixed,
                  reservation:r.fixed,disposition:d.fixed}),finalCtrl.signal)!==true)hold('HOLD_R100_VERIFIER');
              recheck();
            },'HOLD_R100_FINALIZATION_TIMEOUT',reconnectReadTimeoutMs,signal);
          }catch(err){discardReadback();if(err&&err.code)throw err;hold('HOLD_R100_DISPOSITION');}
          finally{finalCtrl.abort();}
        }`);
 replace("typeof host.verifyFreshCanonicalAck!=='function')\n      hold('HOLD_B1_BINDING_TRUSTED_VERIFIER_REQUIRED');",
 "typeof host.verifyFreshCanonicalAck!=='function'||typeof host.requestFinalDisposition!=='function'||typeof host.verifyFinalDisposition!=='function')\n      hold('HOLD_B1_BINDING_TRUSTED_VERIFIER_REQUIRED');");
 return Buffer.from(src,'utf8');
}
module.exports={stageR100};
if(require.main===module){
 if(process.argv.length!==4)throw Error('usage: stage_r100.cjs R86-input staged-output');
 fs.writeFileSync(process.argv[3],stageR100(fs.readFileSync(process.argv[2])),{flag:'wx'});
}
