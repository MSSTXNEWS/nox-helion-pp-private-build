'use strict';
// Release evidence consistency only. No route binding, native authority or provider creation.
const {createHash}=require('node:crypto');
const {readFileSync}=require('node:fs');
const {resolve}=require('node:path');
const {TextDecoder}=require('node:util');
const {makeTimingEvidenceReview}=require('../d3-r113/timing_review.cjs');
const {checkReportedVerdicts}=require('../b2-r112/verdict_consistency.cjs');
const {checkSelectedBrowser}=require('../a3-r113-browser/browser_selection.cjs');
const {checkAdmittedPhysical}=require('./admitted_physical.cjs');
const hash=b=>createHash('sha256').update(b).digest('hex');
const gitBlob=b=>createHash('sha1').update(Buffer.from('blob '+b.length+'\0')).update(b).digest('hex');
const hold=status=>({status,quality_sample:null,metrics:null,reported_review_diagnostics:null,
 native_accepted:false,authentication_verified:false,host_provider_bound:false,
 ack_allowed:false,next_post_allowed:false,training_admitted:false});
const root=resolve(__dirname,'..','d3-r111');
const expected={
 'wire/b0_http_chunked_r76.py':'0f2698d56723bed3615b40ad8c4f98894189ed50',
 'wire/b0_proxy_stream_iter.py':'385906bc443effbea92f38b881c13d04d2103e28',
 'wire/b0_named_delta_encoder.py':'c7d0c351b0239bb7155ffbc8c0362e919ee79cb1',
 'browser/b1_browser_bundle.js':'bd2e154fd2c6007cb315d310e109de470f54f72f',
 'bridge/b3_r64_eof_candidate.js':'66595eac01c562aff4daae68f5d146aaed64cbbe'};
function releasePins(){
 const manifest=readFileSync(resolve(root,'release.json'));
 if(gitBlob(manifest)!=='fd6b4dd58465de1b7874c36f292acd98be7bb6c5')throw Error('manifest');
 const out={};
 for(const [name,blob] of Object.entries(expected)){
  const b=readFileSync(resolve(root,name));if(gitBlob(b)!==blob)throw Error('donor');out[name]=hash(b);
 }
 return {manifest_sha256:hash(manifest),assets:out};
}

/* Detached framing readback is checked for consistency, never treated as authentication.
   A real host verifier must authenticate this receipt independently of the candidate. */
function framingRole(mode){
 const bytes=readFileSync(resolve(root,'framing_source_closure_r86.json'));
 if(gitBlob(bytes)!=='7a2d7e9b3c9abf1a5af2a296e55fb0dcce4c40cc')throw Error('closure pin');
 const map=JSON.parse(new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(bytes));
 if(map.schema!=='NOX_B0_SELECTED_FRAMING_SOURCE_CLOSURE_V1'||
    map.staging_root!=='nox-control/d3-r111'||map.digest_kind!=='git_blob_sha1_source_only')throw Error('closure schema');
 if(mode!=='raw_http_1_1'&&mode!=='framework_managed')return null;
 return map.framing_roles[mode];
}
const exactKeys=(o,keys)=>o!==null&&typeof o==='object'&&!Array.isArray(o)&&
 Object.keys(o).length===keys.length&&keys.every(k=>Object.hasOwn(o,k));
function checkFramingIdentity(detached,d,p,packetPin,payloadPin){
 try{
  const input=detached.framing_receipt_bytes;
  if(!Buffer.isBuffer(input)||!input.length||input.length>65536)return false;
  const bytes=Buffer.from(input);
  if(hash(bytes)!==detached.framing_receipt_sha256)return false;
  const f=JSON.parse(new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(bytes));
  if(!Buffer.from(JSON.stringify(f),'utf8').equals(bytes))return false;
  const role=framingRole(d.framing);
  if(!role||!exactKeys(f,['schema','packet_sha256','payload_sha256','route_sha256',
    'owner_admission_receipt_sha256','framing','adapter_path','process','modules'])||
    f.schema!=='NOX_D3_SELECTED_FRAMING_READBACK_V1'||f.packet_sha256!==packetPin||
    f.payload_sha256!==payloadPin||f.route_sha256!==detached.route_sha256||
    f.owner_admission_receipt_sha256!==p.owner_admission_receipt_sha256||
    f.framing!==d.framing||f.adapter_path!==role.adapter||
    !exactKeys(f.process,['boot_id','pid','start_ticks'])||
    ['boot_id','pid','start_ticks'].some(k=>f.process[k]!==p.process[k])||
    !exactKeys(f.modules,Object.keys(role.modules)))return false;
  for(const [name,blob] of Object.entries(role.modules)){
   const staged=readFileSync(resolve(root,name)),m=f.modules[name],pin=hash(staged);
   if(gitBlob(staged)!==blob||!exactKeys(m,['expected_sha256','installed_sha256','loaded_sha256'])||
      m.expected_sha256!==pin||m.installed_sha256!==pin||m.loaded_sha256!==pin)return false;
  }
  return true;
 }catch{return false;}
}

function makeReleaseEvidenceReview(readDetachedEvidence){
 return (bytes,packet)=>{
  try{
   if(!Buffer.isBuffer(bytes)||bytes.length===0||bytes.length>8*1024*1024||
      typeof packet!=='string'||Buffer.byteLength(packet)>4*1024*1024)return hold('HOLD_ROUTE_INPUT');
   if(typeof readDetachedEvidence!=='function')return hold('HOLD_ROUTE_PROVIDER');
   const raw=Buffer.from(bytes),packetPin=hash(Buffer.from(packet,'utf8')),payloadPin=hash(raw);
   const detached=readDetachedEvidence(packetPin);
   if(!detached||detached.packet_sha256!==packetPin||detached.payload_sha256!==payloadPin||
      !Buffer.isBuffer(detached.route_bytes)||detached.route_bytes.length===0||
      detached.route_bytes.length>65536)return hold('HOLD_ROUTE_DETACHED');
   const routeBytes=Buffer.from(detached.route_bytes);
   if(hash(routeBytes)!==detached.route_sha256)return hold('HOLD_ROUTE_DIGEST');
   const admitted=checkAdmittedPhysical(raw,payloadPin,detached.admitted_envelope_bytes,detached.admitted_envelope_sha256);
   if(admitted.status!=='MATCHED_R83_ADMISSION_OFFLINE')return hold(admitted.status);
   const staged={bytes:readFileSync(resolve(__dirname,'../d3-r111-successor/browser/b1_browser_r100.js'))};
   const selected=checkSelectedBrowser(routeBytes,detached.route_sha256,packet,staged.bytes);
   if(selected.status!=='MATCHED_R88_BROWSER_OFFLINE')return hold(selected.status);
   const d=JSON.parse(new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(routeBytes));
   const pins=releasePins(),a=d.assets;
   if(d.schema!=='NOX_A3_R111_ROUTE_EVIDENCE_V1'||d.packet_sha256!==packetPin||
      d.payload_sha256!==payloadPin||d.manifest_sha256!==pins.manifest_sha256||
      !a||Object.keys(a).length!==Object.keys(pins.assets).length||
      Object.entries(pins.assets).some(([k,v])=>a[k]!==v))return hold('HOLD_ROUTE_RELEASE_PIN');
   // Select exactly one framing owner. A matching descriptor is not authorization.
   const rawMode=d.framing==='raw_http_1_1'&&d.raw_chunk_writer===true&&d.framework_framing===false;
   const managed=d.framing==='framework_managed'&&d.raw_chunk_writer===false&&d.framework_framing===true;
   if(!rawMode&&!managed)return hold('HOLD_ROUTE_FRAMING');
   const [physical]=JSON.parse(raw.toString('utf8')),doc=JSON.parse(packet);
   if(!Array.isArray(physical?.turns)||physical.turns.length!==2||
      !Array.isArray(doc?.turns)||doc.turns.length!==2)return hold('HOLD_ROUTE_SCOPE');
   const browser=selected.browser_sha256,bridge=a['bridge/b3_r64_eof_candidate.js'];
   const p=physical.receipts.expected;
   if(d.bridge_sha256!==bridge||p.bridge_sha256!==bridge||
      d.physical_route!==p.route||d.model_id!==p.model_id||d.physical_dialog_id!==p.dialog_id||
      d.owner_admission_receipt_sha256!==p.owner_admission_receipt_sha256||
      !d.process||['boot_id','pid','start_ticks'].some(k=>d.process[k]!==p.process[k])||
      !Array.isArray(d.turn_request_ids)||d.turn_request_ids.length!==2||
      d.turn_request_ids.some((v,i)=>v!==p.turn_request_ids[i]))return hold('HOLD_ROUTE_PHYSICAL');
   for(let i=0;i<2;i++){
    const t=physical.turns[i],o=JSON.parse(doc.turns[i].observation[0]);
    if(d.symbolic_route!==t.wire.route||d.served_sha256!==t.wire.served_sha256||
       d.server_sha256!==t.wire.server_sha256||d.browser_sha256!==browser||
       o.browser_sha256!==browser||o.served_sha256!==d.served_sha256||
       o.server_sha256!==d.server_sha256)return hold('HOLD_ROUTE_SERVED_BROWSER');
   }
   if(!checkFramingIdentity(detached,d,p,packetPin,payloadPin))return hold('HOLD_ROUTE_FRAMING_IDENTITY');
   const result=checkReportedVerdicts(makeTimingEvidenceReview(pin=>pin===packetPin?detached:null)(raw,packet));
   if(result.status!=='MATCHED_FROZEN_ORDERED_OFFLINE')return {...hold(result.status),offline_browser_timing:null};
   return {...result,status:'MATCHED_R114_JOINT_OFFLINE',selected_browser_sha256:browser,admitted_envelope_sha256:admitted.admitted_envelope_sha256,route_evidence_sha256:detached.route_sha256,
     framing:d.framing,framing_receipt_sha256:detached.framing_receipt_sha256,framing_authenticated:false,host_provider_bound:false,route_authenticated:false,production_ready:false};
  }catch{return hold('HOLD_ROUTE_INVALID');}
 };
}
module.exports={makeReleaseEvidenceReview,releasePins};
