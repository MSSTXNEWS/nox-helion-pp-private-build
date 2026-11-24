'use strict';
// R55 isolated dry-run: NO production or shared file write. Run from repository root.
// node coordination/onepass/b3_r55_cross_turn_pin.cjs [--emit]
const {execFileSync}=require('node:child_process');
const {createHash}=require('node:crypto');
const BASE="0c2228b88cffcb489c1d1f055dabf9aa2ac8d7c9", PATH="coordination/onepass/nox-v135-resonance-owner-bridge.js", BLOB="7e66d4cfcf479d908a1eb9e3bdc86e5899a2b070";
const DONOR="7f6607ce3defa3e2fb743a23538ad618048915a7", DONOR_BLOB="d79093840edea455742c2d2bb151ee2265ce588e";
function pinned(ref,expected){const buf=execFileSync('git',['show',ref+':'+PATH],{maxBuffer:1024*1024}); const sha=createHash('sha1').update('blob '+buf.length+'\0').update(buf).digest('hex');if(sha!==expected)throw Error('BLOB_PIN_MISMATCH '+sha);return buf.toString('utf8');}
function port(source,validator,modelKeys){
  function once(before,after){if(source.split(before).length!==2)throw Error("PREIMAGE_MISMATCH: "+before.slice(0,80));source=source.replace(before,()=>after);}
  once("async function consume(response,emit,signal) {",modelKeys+"\n"+validator+"\nasync function consume(response,emit,signal,id) {");
  once("\t\tif(e.type==='error')throw Error('HOLD_NATIVE_'+String(e.error||'ERROR').slice(0,90));","\t\tif(e.type!=='done'&&'dialog_id'in e&&e.dialog_id!==id)throw Error('HOLD_NATIVE_FRAME_DIALOG_SCOPE');\n\t\tif(e.type==='error')throw Error('HOLD_NATIVE_'+String(e.error||'ERROR').slice(0,90));");
  once("\t\t\tif(doneSeen||typeof e.text!=='string'||answer.length+e.text.length>MAX)","\t\t\tif(modelKeys.some(k=>k in e&&e[k]!==nativeModel))throw Error('HOLD_NATIVE_MODEL_DELTA_DRIFT');\n\t\t\tif(doneSeen||typeof e.text!=='string'||answer.length+e.text.length>MAX)");
  once("\t\t\tdoneSeen=true;done=e;","\t\t\tif(modelKeys.some(k=>k in e&&e[k]!==nativeModel))throw Error('HOLD_NATIVE_MODEL_RECEIPT_DRIFT');\n\t\t\tdoneSeen=true;done=e;");
  once("\t\t\tnativeModel=typeof e.model==='string'\n\t\t\t\t?e.model.replace(/[\\x00-\\x1F\\x7F]/g,' ').trim().slice(0,96)||'UNKNOWN'\n\t\t\t\t:'UNKNOWN';","\t\t\tif(!validNativeModelLabel(e.model)||modelKeys.some(k=>k in e&&e[k]!==e.model))throw Error('HOLD_NATIVE_MODEL_START_LABEL');\n\t\t\tnativeModel=e.model;");
  once("\t\t\t\t},nativeSignal);\n\t\t\t\tstreamDone=true;","\t\t\t\t},nativeSignal,id);\n\t\t\t\tstreamDone=true;");
  once("await consume(upstream,()=>{},signal);","await consume(upstream,()=>{},signal,id);");
  once("const invalidUtf8=e.message==='HOLD_NATIVE_FRAME_UTF8'&&!canceling&&!nativeSignal.aborted;","const invalidUtf8=e.message==='HOLD_NATIVE_FRAME_UTF8'&&!canceling&&!nativeSignal.aborted;\n\t\t\t\tconst identityFailure=/^HOLD_NATIVE_(?:FRAME_DIALOG_SCOPE|MODEL_(?:START_LABEL|DELTA_DRIFT|RECEIPT_DRIFT))$/.test(e.message)&&!canceling&&!nativeSignal.aborted;");
  once("invalidUtf8?'HOLD_NATIVE_FRAME_UTF8':","invalidUtf8?'HOLD_NATIVE_FRAME_UTF8':identityFailure?e.message:");
  return source;
}
async function check(original,candidate,codec){
 const id="a".repeat(32),foreign="b".repeat(32),model="GLM-Flash";
 const preparing={type:"preparing",stream_mode:"NATIVE_TOKEN_STREAM",dialog_id:id},start={type:"start",model,dialog_id:id},delta={type:"delta",text:"ok",dialog_id:id},done={type:"done",dialog_id:id,model};
 const make=(source)=>{const begin=source.indexOf("async function consume("),end=source.indexOf("function sseChat(",begin),prefix=source.includes("const validNativeModelLabel=")?source.slice(source.indexOf("const modelKeys="),begin):"";return new Function("TextDecoder","enc","readNativeOrAbort","MAX","reason",prefix+source.slice(begin,end)+";return consume;")(codec.Decoder,codec.encoder,r=>r.read(),200000,async()=>"ERR");};
 const run=async(fn,frames)=>{let emitted="",error=null,result;const bytes=codec.encoder.encode(frames.map(x=>JSON.stringify(x)).join("\n")+"\n");let sent=false;const response={ok:true,body:{getReader:()=>({read:async()=>sent?{done:true}:(sent=true,{done:false,value:bytes}),cancel:()=>Promise.resolve()})}};try{result=await fn(response,async t=>{emitted+=t},undefined,id)}catch(e){error=e.message}return {emitted,error,model:result?.nativeModel}};
 const before=make(original),after=make(candidate);
 const cases=[
  ["valid",[preparing,start,delta,done],null,"ok"],
  ["optional scopes",[ {type:"preparing",stream_mode:"NATIVE_TOKEN_STREAM"},{type:"start",model},{type:"delta",text:"ok"},{type:"done",dialog_id:id}],null,"ok"],
  ["foreign preparing",[{...preparing,dialog_id:foreign},start,delta,done],"HOLD_NATIVE_FRAME_DIALOG_SCOPE",""],
  ["foreign start",[preparing,{...start,dialog_id:foreign},delta,done],"HOLD_NATIVE_FRAME_DIALOG_SCOPE",""],
  ["null delta scope",[preparing,start,{...delta,dialog_id:null},done],"HOLD_NATIVE_FRAME_DIALOG_SCOPE",""],
  ["start alias drift",[preparing,{...start,native_model_label:"Qwen"},delta,done],"HOLD_NATIVE_MODEL_START_LABEL",""],
  ["unknown start",[preparing,{...start,model:"UNKNOWN"},delta,done],"HOLD_NATIVE_MODEL_START_LABEL",""],
  ["delta model drift",[preparing,start,{...delta,model:"Qwen"},done],"HOLD_NATIVE_MODEL_DELTA_DRIFT",""],
  ["done alias drift",[preparing,start,delta,{...done,native_model_label:"Qwen"}],"HOLD_NATIVE_MODEL_RECEIPT_DRIFT","ok"],
  ["matching aliases",[preparing,{...start,native_model_label:model},{...delta,model,native_model_label:model},{...done,native_model_label:model}],null,"ok"]
 ];
 let oldDefects=0;const results=[];
 for(const [name,frames,error,emitted] of cases){const old=await run(before,frames),next=await run(after,frames);if(error&&old.error===null)oldDefects++;if(next.error!==error||next.emitted!==emitted||(!error&&next.model!==model))throw Error(name+JSON.stringify(next));results.push(name);}
 if(oldDefects!==7)throw Error("old reproductions "+oldDefects);
 new Function(candidate);
 const protect=(src)=>src.slice(src.indexOf("  function ownerDialogReceipt"),src.indexOf("  async function readNativeOrAbort"));
 if(protect(original)!==protect(candidate))throw Error("owner receipt/verifyAccepted changed");
 const stop=(src)=>src.slice(src.indexOf("function sseChat"),src.indexOf("const canSegment="));
 if(stop(original)!==stop(candidate))throw Error("STOP/409 admission changed");
 return {passed:results.length,oldDefects,results,receiptAndAdmissionUnchanged:true};
}

function crossTurn(source){
  function once(before,after){if(source.split(before).length!==2)throw Error('R55_PREIMAGE '+before.slice(0,100));source=source.replace(before,()=>after);}
  once("const modelKeys=", "const dialogModelPins=new Map();\nfunction modelPinAdmission(id){if(!dialogModelPins.has(id)&&dialogModelPins.size>=128)throw Error('HOLD_DIALOG_PIN_CAPACITY');}\nfunction assertDialogModel(id,model){const pinned=dialogModelPins.get(id);if(pinned!==undefined&&pinned!==model)throw Error('HOLD_DIALOG_MODEL_DRIFT');}\nfunction commitDialogModel(id,model){modelPinAdmission(id);assertDialogModel(id,model);if(!validNativeModelLabel(model))throw Error('HOLD_NATIVE_MODEL_START_LABEL');dialogModelPins.set(id,model);}\nconst modelKeys=");
  once("\t\t\tnativeModel=e.model;","\t\t\tassertDialogModel(id,e.model);\n\t\t\tnativeModel=e.model;");
  once("const id=await dialogId(data,nativeSignal);","const id=await dialogId(data,nativeSignal);\n\t\t\t\tmodelPinAdmission(id);");
  once("const id=await dialogId(data,signal);","const id=await dialogId(data,signal);\n      modelPinAdmission(id);");
  once("const s03Integrated=await verifyAccepted(receipt,id,data.message,answer,nativeSignal);\n\t\t\t\tif(nativeSignal.aborted)throw Error('STREAM_STOP_REQUESTED');","const s03Integrated=await verifyAccepted(receipt,id,data.message,answer,nativeSignal);\n\t\t\t\tif(nativeSignal.aborted)throw Error('STREAM_STOP_REQUESTED');\n\t\t\t\tcommitDialogModel(id,receipt.native_model_label);");
  once("const s03Integrated=await verifyAccepted(receipt,id,data.message,answer,signal);\n      if(signal?.aborted)throw Error('STREAM_STOP_REQUESTED');","const s03Integrated=await verifyAccepted(receipt,id,data.message,answer,signal);\n      if(signal?.aborted)throw Error('STREAM_STOP_REQUESTED');\n      commitDialogModel(id,nativeModel);");
  once("const identityFailure=/^HOLD_NATIVE_(?:FRAME_DIALOG_SCOPE|MODEL_(?:START_LABEL|DELTA_DRIFT|RECEIPT_DRIFT))$/.test(e.message)&&!canceling&&!nativeSignal.aborted;","const identityFailure=/^(?:HOLD_NATIVE_(?:FRAME_DIALOG_SCOPE|MODEL_(?:START_LABEL|DELTA_DRIFT|RECEIPT_DRIFT))|HOLD_DIALOG_MODEL_DRIFT)$/.test(e.message)&&!canceling&&!nativeSignal.aborted;");
  return source;
}
async function checkCrossTurn(r54,after,codec){
  const id='a'.repeat(32),other='b'.repeat(32),model='GLM-Flash',drift='Qwen';
  const make=(src)=>{
    const begin=src.indexOf('async function consume('),end=src.indexOf('function sseChat(',begin),start=src.indexOf('const dialogModelPins=');
    const prefix=src.slice(start>=0?start:src.indexOf('const modelKeys='),begin);
    return new Function('TextDecoder','enc','readNativeOrAbort','MAX','reason',prefix+src.slice(begin,end)+';return {consume,commit:typeof commitDialogModel==="function"?commitDialogModel:null,admit:typeof modelPinAdmission==="function"?modelPinAdmission:null};')(codec.Decoder,codec.encoder,r=>r.read(),200000,async()=>'ERR');
  };
  const run=async(impl,dialog,label)=>{
    const frames=[{type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM',dialog_id:dialog},{type:'start',model:label,dialog_id:dialog},{type:'delta',text:'ok',dialog_id:dialog},{type:'done',dialog_id:dialog,model:label}];
    const bytes=codec.encoder.encode(frames.map(JSON.stringify).join('\n')+'\n');let sent=false,emitted='',error=null,result;
    const response={ok:true,body:{getReader:()=>({read:async()=>sent?{done:true}:(sent=true,{done:false,value:bytes}),cancel:()=>Promise.resolve()})}};
    try{result=await impl.consume(response,async t=>{emitted+=t},undefined,dialog)}catch(e){error=e.message}
    return {emitted,error,model:result?.nativeModel};
  };
  const before=make(r54),next=make(after);let passed=0;
  function ok(cond,name){if(!cond)throw Error(name);passed++}
  ok((await run(before,id,model)).emitted==='ok'&&(await run(before,id,drift)).emitted==='ok','R54 drift reproduction');
  ok((await run(next,id,model)).emitted==='ok','initial unpinned turn');
  ok((await run(next,id,drift)).emitted==='ok','unverified turn does not pin');
  next.commit(id,model);
  ok((await run(next,id,model)).emitted==='ok','same model next turn');
  const wrong=await run(next,id,drift);
  ok(wrong.error==='HOLD_DIALOG_MODEL_DRIFT'&&wrong.emitted==='','reject before first token');
  ok((await run(next,other,drift)).emitted==='ok','other dialog independent');
  let e;try{next.commit(id,drift)}catch(x){e=x.message}ok(e==='HOLD_DIALOG_MODEL_DRIFT','conflicting commit');
  for(let i=0;i<127;i++)next.commit('slot'+i,model);
  next.admit(id);let cap;try{next.admit(other)}catch(x){cap=x.message}ok(cap==='HOLD_DIALOG_PIN_CAPACITY','bounded pins and existing admitted');
  const protect=s=>s.slice(s.indexOf('  function ownerDialogReceipt'),s.indexOf('  async function readNativeOrAbort'));
  ok(protect(r54)===protect(after),'independent receipt verification unchanged');
  ok(after.includes('},nativeSignal,id);')&&after.includes('consume(upstream,()=>{},signal,id);'),'SSE and JSON consume scope');
  ok(after.indexOf('commitDialogModel(id,receipt.native_model_label);')>after.indexOf('await verifyAccepted(receipt,id,data.message,answer,nativeSignal)')&&after.indexOf('commitDialogModel(id,nativeModel);')>after.indexOf('await verifyAccepted(receipt,id,data.message,answer,signal)'),'pin only after accepted readback');
  new Function(after);
  return {passed,oldDriftReproduced:true};
}
(async()=>{const before=pinned(BASE,BLOB),donor=pinned(DONOR,DONOR_BLOB);const validator=donor.match(/^const validNativeModelLabel=.*;$/m)[0],keys=donor.match(/^const modelKeys=.*;$/m)[0];const first=port(before,validator,keys),after=crossTurn(first),codec={Decoder:TextDecoder,encoder:new TextEncoder()};const r54=await check(before,first,codec),r55=await checkCrossTurn(first,after,codec);console.error(JSON.stringify({r54,r55,sourceBytes:Buffer.byteLength(before),candidateBytes:Buffer.byteLength(after),candidateSha256:createHash('sha256').update(after).digest('hex')}));if(process.argv.includes('--emit'))process.stdout.write(after);})().catch(e=>{console.error(e);process.exitCode=1;});
