/* NOX CINEMA PACK01 — canonical events.v3 admission for 50 secondary-screen controls.
 * This is a purely visual parser. Security authority stays in the native host:
 * only native-subscribed, identity/receipt-verified envelopes may reach this module.
 * No direct browser message or website JSON can grant "live/training" status.
 */
const ID=/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const SHA=/^[0-9a-f]{64}$/i;
const SCHEMA="NOX-INSTALLER-EVENT-v3";
const PACKAGES=Object.freeze({1:"P01",2:"P02",3:"P03",4:"P04",5:"P05",6:"E06"});
const EVENT_TYPES=new Set(["task.started","task.progress","task.completed","task.failed",
  "training.step","checkpoint.saved","model.stopped"]);
const MAX_AGE_MS=30000;

export function admitNativeVisualEvent(packet,catalog,{now=Date.now()}={}){
  if(!packet||typeof packet!=="object"||
    !catalog||!Array.isArray(catalog.actions)||catalog.actions.length!==50||
    !Number.isFinite(now))return null;
  // Packet is emitted only through a privileged, native-host-verified subscription.
  // routeId is bound to the owner session by that native host (not by a web page).
  const {routeId,raw}=packet;
  const action=catalog.actions.find(x=>x.routeId===routeId);
  if(!action||!raw||raw.schema!==SCHEMA||raw.evidence_verified!==true||
    !EVENT_TYPES.has(raw.event_type)||
    ![raw.run_id,raw.event_id,raw.task_id,raw.action_id].every(v=>typeof v==="string"&&ID.test(v))||
    raw.package_id!==PACKAGES[action.owner]||
    !Number.isSafeInteger(raw.event_sequence)||raw.event_sequence<1||
    typeof raw.receipt_sha256!=="string"||!SHA.test(raw.receipt_sha256)||
    typeof raw.timestamp_utc!=="string")return null;
  const occurred=Date.parse(raw.timestamp_utc);
  if(!Number.isFinite(occurred)||occurred>now+5000||now-occurred>MAX_AGE_MS)return null;
  if(raw.numerator!==undefined&&raw.numerator!==null){
    if(!Number.isSafeInteger(raw.numerator)||raw.numerator<0||
      !Number.isSafeInteger(raw.denominator)||raw.denominator<1||
      raw.numerator>raw.denominator)return null;
  }
  let state=null;
  switch(raw.event_type){
    case "task.started":state="running";break;
    case "task.progress":
      // Do not translate arbitrary task.progress into downloading/training.
      if(action.owner===3&&/^(pull|download|model[._-](?:pull|download))/.test(raw.action_id))
        state="downloading";
      break;
    case "training.step":
    case "checkpoint.saved":
      if(action.owner===4&&/^(training|train|qlora|lora)[._:-]/.test(raw.action_id))
        state="training";
      break;
    case "task.completed":state="completed";break;
    case "task.failed":state="error";break;
    case "model.stopped":if(action.owner===3||action.owner===4)state="stopped";break;
  }
  if(!state)return null;
  return Object.freeze({
    routeId,runId:raw.run_id,eventId:raw.event_id,
    sequence:raw.event_sequence,state,occurred,
    expires:occurred+MAX_AGE_MS,
    progress:(raw.numerator!==undefined&&raw.numerator!==null)
      ?Object.freeze({numerator:raw.numerator,denominator:raw.denominator}):null
  });
}

export const CINEMA_EVENT_CONTRACT=Object.freeze({
  schema:SCHEMA,maxAgeMs:MAX_AGE_MS,subscribeName:"subscribeVerifiedVisualEvents",
  sourceOnly:true,defaultDisabled:true,allowedPackages:PACKAGES
});
