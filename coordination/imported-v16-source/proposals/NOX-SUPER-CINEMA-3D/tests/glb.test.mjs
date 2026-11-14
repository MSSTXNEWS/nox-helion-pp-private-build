import test from "node:test";
import assert from "node:assert/strict";
import {webcrypto} from "node:crypto";
import {validateGLBReceipt,inspectGLB,parseApprovedGLB} from "../src/glb.mjs";
function makeGLB(graph){
 const json=JSON.stringify(graph),raw=new TextEncoder().encode(json);
 const pad=(4-raw.length%4)%4,bytes=new Uint8Array(20+raw.length+pad),view=new DataView(bytes.buffer);
 view.setUint32(0,0x46546c67,true);view.setUint32(4,2,true);view.setUint32(8,bytes.length,true);
 view.setUint32(12,raw.length+pad,true);view.setUint32(16,0x4e4f534a,true);
 bytes.set(raw,20);for(let i=0;i<pad;i++)bytes[20+raw.length+i]=32;
 return bytes.buffer;
}
const scene={asset:{version:"2.0"},scenes:[{nodes:[]}],scene:0,nodes:[]};
test("self contained glb schema without external references accepted",()=>{
 const bytes=makeGLB(scene);assert.equal(inspectGLB(bytes),true);
});
test("bad GLB / redirected GLB resource blocked",()=>{
 const bytes=makeGLB({...scene,images:[{uri:"https://evil.example/x.png"}]});
 assert.throws(()=>inspectGLB(bytes),/GLB_EXTERNAL_RESOURCE_DENIED/);
 const broken=new ArrayBuffer(8);assert.throws(()=>inspectGLB(broken),/GLB_INVALID_SIZE/);
});
test("approved exact-SHA minimal GLB parses through official GLTFLoader",async()=>{
 const bytes=makeGLB(scene);
 const digest=Array.from(new Uint8Array(await webcrypto.subtle.digest("SHA-256",bytes)),x=>x.toString(16).padStart(2,"0")).join("");
 const asset={id:"approved-stage-01",kind:"glb",approved:true,sha256:digest,license:"NOX_ORIGINAL"};
 assert.equal(validateGLBReceipt(asset),true);
 const loaded=await parseApprovedGLB(asset,bytes,{cryptoAPI:webcrypto});
 assert.equal(loaded.isObject3D,true);
 await assert.rejects(parseApprovedGLB({...asset,sha256:"f".repeat(64)},bytes,{cryptoAPI:webcrypto}),/GLB_SHA256_MISMATCH/);
});
test("unapproved GLB / rights missing denied",()=>{
 const bad={id:"stage-01",kind:"glb",approved:false,sha256:"a".repeat(64),license:"CC0-1.0"};
 assert.throws(()=>validateGLBReceipt(bad),/GLB_OWNER_RIGHTS_HOLD/);
 assert.throws(()=>validateGLBReceipt({...bad,approved:true,license:"LICENSED_OWNER"}),/GLB_OWNER_RIGHTS_HOLD/);
});
