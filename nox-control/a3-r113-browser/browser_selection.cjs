'use strict';
// Independent browser-selection consistency only; no provider or admission.
const {createHash}=require('node:crypto');
const {readFileSync}=require('node:fs');
const {resolve}=require('node:path');
const {TextDecoder}=require('node:util');
const sha=b=>createHash('sha256').update(b).digest('hex');
const blob=b=>createHash('sha1').update(Buffer.from('blob '+b.length+'\0')).update(b).digest('hex');
const read=p=>readFileSync(resolve(__dirname,p));
const exact=(b,p)=>Buffer.isBuffer(b)&&blob(b)===p;
const decoder=new TextDecoder('utf-8',{fatal:true,ignoreBOM:true});
const parse=b=>JSON.parse(decoder.decode(b));
const roleBlob='a3c10fa7ee627d3f5d7517e55f36d8f68005b1e4';
const selected='37a756fdc6544f8b5d73425c83221bb958504bd3199dd6245aa4d4b62549651f';
const old='e7140c983b646b7544f95774491e718bed06880ac6a6e21b8f51980cdec5542b';
const manifest='d3d7035db09ef85a7ccfcac64c9bdcf29778ea4a66a076be33c61e2454312650';
const hex=v=>typeof v==='string'&&/^[0-9a-f]{64}$/.test(v);
const hold=status=>({status,native_accepted:false,authentication_verified:false,host_provider_bound:false,ack_allowed:false,next_post_allowed:false,training_admitted:false,production_ready:false});
function stageSelectedBrowser(){
 const role=read('browser_role_input.json'),stager=read('stage_r100.cjs');
 const base=read('../d3-r111/release.json'),original=read('../d3-r111/browser/b1_browser_bundle.js');
 if(!exact(role,roleBlob)||!exact(stager,'157270b88577fc0c4a92bf45f07f041ef89b1251')||
    !exact(base,'fd6b4dd58465de1b7874c36f292acd98be7bb6c5')||sha(base)!==manifest||
    !exact(original,'bd2e154fd2c6007cb315d310e109de470f54f72f')||sha(original)!==old)throw Error('HOLD_R88_SOURCE_PIN');
 const bytes=require('./stage_r100.cjs').stageR100(original);
 if(bytes.length!==89135||sha(bytes)!==selected)throw Error('HOLD_R88_SELECTED_PIN');
 return {bytes,role_sha256:sha(role),browser_sha256:selected,historical_browser_sha256:old,manifest_sha256:manifest};
}
// Call before the sole joint route/timing review. Do not rewrite original R111 assets or observations.
function checkSelectedBrowser(routeBytes,routeDigest,packet,stagedBytes){
 try{
  if(!Buffer.isBuffer(routeBytes)||routeBytes.length===0||routeBytes.length>65536||
     sha(routeBytes)!==routeDigest||typeof packet!=='string'||Buffer.byteLength(packet)>4*1024*1024||
     !Buffer.isBuffer(stagedBytes)||stagedBytes.length!==89135||sha(stagedBytes)!==selected)
   return hold('HOLD_R88_INPUT');
  const role=read('browser_role_input.json');
  if(!exact(role,roleBlob))return hold('HOLD_R88_ROLE_PIN');
  const d=parse(routeBytes),doc=JSON.parse(packet);
  if(d.manifest_sha256!==manifest||d.successor_role_sha256!==sha(role)||
     d.assets?.['browser/b1_browser_bundle.js']!==old||d.browser_sha256!==selected||
     d.packet_sha256!==sha(Buffer.from(packet,'utf8')))
   return hold('HOLD_R88_ROUTE_PIN');
  if(!Array.isArray(doc.turns)||doc.turns.length!==2||
     !hex(d.served_sha256)||!hex(d.server_sha256)||!hex(d.bridge_sha256))
   return hold('HOLD_R88_SCOPE');
  const observationIds=new Set();
  for(const t of doc.turns){
   const pair=t.observation;
   if(!Array.isArray(pair)||pair.length!==2||typeof pair[0]!=='string'||
      sha(Buffer.from(pair[0],'utf8'))!==pair[1])return hold('HOLD_R88_OBSERVATION_DIGEST');
   const o=JSON.parse(pair[0]);
   if(o.browser_sha256!==selected||o.served_sha256!==d.served_sha256||
      o.server_sha256!==d.server_sha256||typeof o.observation_id!=='string'||
      !o.observation_id||observationIds.has(o.observation_id))return hold('HOLD_R88_OBSERVATION_PIN');
   observationIds.add(o.observation_id);
  }
  return {...hold('MATCHED_R88_BROWSER_OFFLINE'),browser_sha256:selected,role_sha256:sha(role)};
 }catch{return hold('HOLD_R88_INVALID');}
}
module.exports={stageSelectedBrowser,checkSelectedBrowser};
