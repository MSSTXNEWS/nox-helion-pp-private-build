'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
async function run(original,candidate,env){const {Decoder,encoder,clock,set,clear}=env;const load=s=>Function("TextDecoder","enc","performance","setTimeout","clearTimeout","MAX",s.slice(s.indexOf("async function readNativeOrAbort"),s.indexOf("function sseChat"))+";return consume;")(Decoder,encoder,clock,set,clear,1000000);const old=load(original),now=load(candidate);const line=x=>JSON.stringify(x)+"\n";const prefix=line({type:"preparing",stream_mode:"NATIVE_TOKEN_STREAM"})+line({type:"start",model:"GLM-test"})+line({type:"delta",text:"hello"});const done=line({type:"done",exchange_id:"fixture",model:"GLM-test"});const EOF=Symbol(),STALL=Symbol();async function runCase(consume,parts){let i=0,cancel=0,eof=0,released=0,tokens=[],error="",result;const reader={async read(){const x=parts[i++];if(x===EOF){eof++;return {done:true}}if(x===STALL)return new Promise(()=>{});if(typeof x!=="string")throw Error("unexpected read");return {done:false,value:encoder.encode(x)}},async cancel(){cancel++},releaseLock(){released++}};try{result=await consume({ok:true,body:{getReader:()=>reader}},x=>tokens.push(x),undefined,"fixture-dialog")}catch(e){error=e.message}return {error,result,cancel,eof,released,tokens,reads:i}}
const results=[];function check(name,condition){if(!condition)throw Error("FAIL "+name);results.push(name)}
let x=await runCase(old,[prefix,done,EOF]);check("R61 reproduces premature cancel",x.eof===0&&x.cancel===1&&x.result?.answer==="hello");
x=await runCase(now,[prefix,done,EOF]);check("true EOF before success",x.eof===1&&x.cancel===0&&x.released===1&&x.result?.answer==="hello");
x=await runCase(now,[prefix,done," \r\n",EOF]);check("bounded whitespace then EOF",x.eof===1&&x.cancel===0&&x.result?.answer==="hello");
x=await runCase(now,[prefix,done,line({type:"delta",text:"late"}),EOF]);check("late delta rejected",x.error==="HOLD_NATIVE_TRAILING_FRAME_AFTER_DONE"&&x.cancel===1&&x.tokens.join("")==="hello"&&!x.result);
x=await runCase(now,[prefix,done,done,EOF]);check("duplicate done rejected",x.error==="HOLD_DUPLICATE_DONE"&&x.cancel===1&&!x.result);
x=await runCase(now,[prefix,done,'{"type":',EOF]);check("partial trailing frame rejected",x.error==="HOLD_NATIVE_TRAILING_FRAME_AFTER_DONE"&&!x.result);
x=await runCase(now,[prefix,done," ".repeat(4097),EOF]);check("tail byte cap",x.error==="HOLD_NATIVE_TRAILING_FRAME_AFTER_DONE"&&!x.result);
x=await runCase(now,[prefix,EOF]);check("EOF without done rejected",x.error==="HOLD_INCOMPLETE_NATIVE_RESPONSE"&&!x.result);
x=await runCase(now,[prefix,done,STALL]);check("missing EOF bounded timeout",x.error==="HOLD_NATIVE_EOF_TIMEOUT"&&x.cancel===1&&!x.result);
return results}
const original=fs.readFileSync(path.join(__dirname,'b3_r61_release_candidate.js'),'utf8'),candidate=fs.readFileSync(path.join(__dirname,'b3_r64_eof_candidate.js'),'utf8');
const sha=s=>crypto.createHash('sha256').update(s).digest('hex');
if(sha(original)!=='9cd1cd1ab96a01b295418b59d53669b742d804520af15e3da648716b02427ef3'||Buffer.byteLength(candidate)>25454)throw Error('pin/cap');
run(original,candidate,{Decoder:TextDecoder,encoder:new TextEncoder(),clock:performance,set:setTimeout,clear:clearTimeout}).then(t=>{console.log(JSON.stringify({source_pass:t.length,cases:t,candidate_sha256:sha(candidate),bytes:Buffer.byteLength(candidate),native_accepted:false}));},e=>{console.error(e);process.exitCode=1;});
