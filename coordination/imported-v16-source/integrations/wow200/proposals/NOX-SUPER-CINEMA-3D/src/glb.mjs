/* NOX 3D: strictly in-memory, byte-checked, owner-approved self-contained GLB.
 * No URL loader, no external textures, no filesystem access or network requests.
 */
import {GLTFLoader} from "three/addons/loaders/GLTFLoader.js";
const SHA=/^[0-9a-f]{64}$/i;
const MAX_GLB=32*1024*1024;
export function validateGLBReceipt(asset){
 if(!asset||asset.approved!==true||asset.kind!=="glb"||
  typeof asset.id!=="string"||!/^[a-z][a-z0-9_-]{1,63}$/.test(asset.id)||
  !SHA.test(asset.sha256||"")||
  !["CC0-1.0","NOX_ORIGINAL","LICENSED_OWNER"].includes(asset.license)||
  (asset.license==="LICENSED_OWNER"&&asset.consent!==true))
  throw Error("GLB_OWNER_RIGHTS_HOLD");
 return true;
}
export function inspectGLB(bytes){
 if(!(bytes instanceof ArrayBuffer)||bytes.byteLength<20||bytes.byteLength>MAX_GLB)
  throw Error("GLB_INVALID_SIZE");
 const view=new DataView(bytes);
 if(view.getUint32(0,true)!==0x46546c67||view.getUint32(4,true)!==2||view.getUint32(8,true)!==bytes.byteLength)
  throw Error("INVALID_GLB_HEADER");
 const jsonSize=view.getUint32(12,true);
 if(view.getUint32(16,true)!==0x4e4f534a||jsonSize<=0||jsonSize>500_000||20+jsonSize>bytes.byteLength)
  throw Error("GLB_JSON_INVALID");
 const data=new Uint8Array(bytes,20,jsonSize);
 let graph;
 try{graph=JSON.parse(new TextDecoder("utf-8",{fatal:true}).decode(data))}catch{throw Error("GLB_JSON_INVALID")}
 if(graph.asset?.version!=="2.0"||!Array.isArray(graph.scenes)||graph.scenes.length<1)
  throw Error("GLB_SCHEMA_INVALID");
 // No external buffers, images or URIs may be loaded in this optional renderer.
 if((graph.buffers||[]).some(b=>typeof b.uri==="string")||
    (graph.images||[]).some(b=>typeof b.uri==="string")||
    (graph.extensionsUsed||[]).some(x=>typeof x!=="string"))
  throw Error("GLB_EXTERNAL_RESOURCE_DENIED");
 return true;
}
export async function parseApprovedGLB(asset,bytes,{cryptoAPI=globalThis.crypto}={}){
 validateGLBReceipt(asset);inspectGLB(bytes);
 if(!cryptoAPI?.subtle?.digest)throw Error("WEBCRYPTO_REQUIRED");
 const digest=Array.from(new Uint8Array(await cryptoAPI.subtle.digest("SHA-256",bytes)),x=>x.toString(16).padStart(2,"0")).join("");
 if(digest!==asset.sha256.toLowerCase())throw Error("GLB_SHA256_MISMATCH");
 const gltf=await new Promise((resolve,reject)=>{
  new GLTFLoader().parse(bytes,"",resolve,reject);
 });
 if(!gltf?.scene||!gltf.scene.isObject3D)throw Error("GLB_PARSE_INCOMPLETE");
 return gltf.scene;
}
