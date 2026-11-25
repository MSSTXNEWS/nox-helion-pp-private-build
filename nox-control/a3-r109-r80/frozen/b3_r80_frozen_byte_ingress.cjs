'use strict';
// B5 R80 immutable byte boundary. expectedSha256 MUST be provided by a
// separately authenticated evidence channel. Equality is not authentication.
const {createHash,timingSafeEqual}=require('node:crypto');
const {TextDecoder}=require('node:util');
const {checkRetainedPair}=require('./b3_r71_physical_terminal_composition.cjs');
const MAX_BYTES=8*1024*1024;
const flags=['native_accepted','authentication_verified','ack_allowed','next_post_allowed'];
const hold=reason=>({status:'HOLD',reason,consistent:false,native_accepted:false,authentication_verified:false,ack_allowed:false,next_post_allowed:false});
function checkFrozenPayload(bytes,expectedSha256){
 try{
  if(!Buffer.isBuffer(bytes)||bytes.length===0||bytes.length>MAX_BYTES)return hold('FROZEN_BYTES_REQUIRED');
  if(typeof expectedSha256!=='string'||! /^[a-f0-9]{64}$/.test(expectedSha256))return hold('DETACHED_PAYLOAD_PIN_REQUIRED');
  const snapshot=Buffer.from(bytes);
  const digest=createHash('sha256').update(snapshot).digest();
  if(!timingSafeEqual(digest,Buffer.from(expectedSha256,'hex')))return hold('FROZEN_PAYLOAD_SHA256');
  if(snapshot[0]===0xef&&snapshot[1]===0xbb&&snapshot[2]===0xbf)return hold('FROZEN_UTF8_BOM');
  const args=JSON.parse(new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(snapshot));
  if(!Array.isArray(args)||args.length!==3)return hold('FROZEN_PAYLOAD_SHAPE');
  const result=checkRetainedPair(...args);
  if(result.status!=='CONSISTENT_PHYSICAL_RETAINED_PAIR_ONLY'||result.consistent!==true||!flags.every(k=>result[k]===false))return hold('FROZEN_PAIR_'+(result.reason||'HOLD'));
  return {...result,payload_sha256:digest.toString('hex')};
 }catch{return hold('FROZEN_INVALID_INPUT');}
}
module.exports={checkFrozenPayload};
