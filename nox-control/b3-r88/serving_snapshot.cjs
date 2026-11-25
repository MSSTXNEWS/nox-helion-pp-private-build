'use strict';
// B3 source-only donor: one detached top-level identity snapshot, never authentication.
const {types}=require('node:util');
const pins=['packet_sha256','payload_sha256','route_sha256','admitted_envelope_sha256','framing_receipt_sha256'];
const fields=['route_bytes','admitted_envelope_bytes','framing_receipt_bytes'];
const typed=Object.getPrototypeOf(Uint8Array.prototype);
const get=(v,k)=>Object.getOwnPropertyDescriptor(typed,k).get.call(v);
function captureServingIdentity(input){
 try{
  if(!input||typeof input!=='object'||types.isProxy(input))return null;
  const proto=Object.getPrototypeOf(input);
  if(proto!==Object.prototype&&proto!==null)return null;
  const ds=Object.getOwnPropertyDescriptors(input),out=Object.create(null);
  for(const k of Reflect.ownKeys(ds)){
   const d=ds[k];if(typeof k!=='string'||!Object.hasOwn(d,'value'))return null;
   out[k]=d.value;
  }
  for(const k of pins)if(typeof out[k]!=='string'||! /^[a-f0-9]{64}$/.test(out[k]))return null;
  for(const k of fields){
   const v=out[k];if(!v||types.isProxy(v)||!Buffer.isBuffer(v))return null;
   const ab=get(v,'buffer'),n=get(v,'byteLength'),off=get(v,'byteOffset');
   if(types.isSharedArrayBuffer(ab)||n===0||n>65536)return null;
   out[k]=Buffer.from(new Uint8Array(ab,off,n));
  }
  // Other own data fields are retained for their dedicated validators; no deep host claim.
  return Object.freeze(out);
 }catch{return null;}
}
module.exports={captureServingIdentity};
