'use strict';
const assert=require('node:assert/strict');
const {captureServingIdentity:capture}=require('./serving_snapshot.cjs');
const pin='ab'.repeat(32),other='cd'.repeat(32);
const fresh=()=>({packet_sha256:pin,payload_sha256:pin,route_sha256:pin,admitted_envelope_sha256:pin,framing_receipt_sha256:pin,route_bytes:Buffer.from('route'),admitted_envelope_bytes:Buffer.from('admission'),framing_receipt_bytes:Buffer.from('framing'),host:{turns:[]}});
let n=0;function test(f){f();n++;}
test(()=>{const a=fresh(),b=capture(a);assert(b);assert(Object.isFrozen(b));assert.equal(b.host,a.host);for(const k of ['route_bytes','admitted_envelope_bytes','framing_receipt_bytes']){assert(Buffer.isBuffer(b[k]));assert.deepEqual(b[k],a[k]);a[k].fill(0);assert.notDeepEqual(b[k],a[k]);}});
for(const k of ['route_sha256','framing_receipt_sha256','admitted_envelope_sha256','route_bytes','admitted_envelope_bytes','framing_receipt_bytes'])test(()=>{const a=fresh(),v=a[k];let reads=0;Object.defineProperty(a,k,{get(){return ++reads===1?v:other}});assert.equal(capture(a),null);assert.equal(reads,0);});
test(()=>{const a=fresh();delete a.route_sha256;assert.equal(capture(a),null);});
test(()=>{const a=fresh();a.route_bytes=Buffer.alloc(65537);assert.equal(capture(a),null);});
test(()=>{const a=fresh();a.route_bytes=Buffer.from(new SharedArrayBuffer(3));assert.equal(capture(a),null);});
test(()=>{let calls=0;const a=new Proxy(fresh(),{getOwnPropertyDescriptor(){calls++;throw Error('trap')}});assert.equal(capture(a),null);assert.equal(calls,0);});
test(()=>{const a=fresh();a.route_bytes=Buffer.alloc(0);assert.equal(capture(a),null);});
console.log(`${n}/${n} serving snapshot cases PASS; synthetic source only`);
