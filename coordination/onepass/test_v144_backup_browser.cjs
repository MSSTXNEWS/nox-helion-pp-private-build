'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const file=process.argv[2];
if(!file)throw Error('Provide patched original workspace-pages.js path');
const source=fs.readFileSync(file,'utf8');
async function one(opts){
 const calls=[];
 const data=opts.data || {};
 const sandbox={
  window:{NOX_NATIVE_OWNER:opts.native!==false,
   NoxWorkspace:{native:opts.native!==false,request:async(path,body)=>{
     calls.push([path,body]);
     if(path==='/api/nox/status')return data.status || {host:'NOX_CHAT_V24.1',status:'READY',owner_authenticated:true,windows_owner_pc:true};
     if(path==='/api/install/capabilities')return data.ability || {status:'READY',windows_owner_pc:true,owner_authenticated:true,backup_supported:true};
     if(path==='/api/install/backup')return data.backup || {status:'READY',sha256_verified:true,backup_sha256:'b'.repeat(64)};
     throw Error('UNKNOWN_ROUTE '+path);
    }}},
  document:{getElementById(){return null},body:{dataset:{page:'install'}}},
  location:{protocol:opts.protocol||'http:',hostname:opts.host||'127.0.0.1',port:opts.port||'8766'},
  URL,console,Promise,Error
 };
 sandbox.workspace=sandbox.window.NoxWorkspace;
 sandbox.api=sandbox.workspace.request;
 vm.runInNewContext(source,sandbox,{timeout:2000});
 assert.equal(typeof sandbox.window.NOX_WINDOWS_BACKUP_V144?.backup,'function');
 try{return {calls,result:await sandbox.window.NOX_WINDOWS_BACKUP_V144.backup(),err:null}}
 catch(e){return {calls,err:String(e.message||e),result:null}}
}
(async()=>{
 let r=await one({host:'gpu.vast.ai'});
 assert.match(r.err,/HOLD_WINDOWS_BACKUP_WRONG_HOST_OR_ANONYMOUS/);assert.equal(r.calls.length,0);
 r=await one({port:'18775'});
 assert.match(r.err,/HOLD_WINDOWS_BACKUP_WRONG_HOST_OR_ANONYMOUS/);assert.equal(r.calls.length,0);
 r=await one({native:false});
 assert.match(r.err,/HOLD_WINDOWS_BACKUP_WRONG_HOST_OR_ANONYMOUS/);assert.equal(r.calls.length,0);
 r=await one({data:{status:{host:'NOX_CHAT_V24.1',status:'READY'}}});
 assert.match(r.err,/HOLD_WINDOWS_BACKUP_OWNER_IDENTITY_UNVERIFIED/);assert.deepEqual(r.calls.map(x=>x[0]),['/api/nox/status']);
 // Source-only regression: the real 92-route map labels /api/nox/status
 // OneHost-owned. A READY OneHost response is not Windows PC authority.
 r=await one({data:{status:{host:'NOX_CHAT_V24.1',status:'READY',owner_authenticated:true}}});
 assert.match(r.err,/HOLD_WINDOWS_BACKUP_OWNER_IDENTITY_UNVERIFIED/);
 assert.deepEqual(r.calls.map(x=>x[0]),['/api/nox/status']);
 r=await one({data:{status:{host:'EXISTING_NATIVE_ONEHOST',status:'READY',owner_authenticated:true}}});
 assert.match(r.err,/HOLD_WINDOWS_BACKUP_OWNER_IDENTITY_UNVERIFIED/);assert.equal(r.calls.length,1);
 r=await one({data:{ability:{status:'READY',windows_owner_pc:false,owner_authenticated:true,backup_supported:true}}});
 assert.match(r.err,/HOLD_WINDOWS_BACKUP_OWNER_CAPABILITY_UNVERIFIED/);assert.equal(r.calls.length,2);
 r=await one({data:{backup:{status:'READY',sha256_verified:false,backup_sha256:'b'.repeat(64)}}});
 assert.match(r.err,/HOLD_WINDOWS_BACKUP_NATIVE_SHA_RECEIPT_UNVERIFIED/);assert.equal(r.calls.length,3);
 r=await one({});
 assert.equal(r.err,null);assert.equal(r.result.backup_sha256,'b'.repeat(64));
 assert.deepEqual(r.calls.map(x=>x[0]),['/api/nox/status','/api/install/capabilities','/api/install/backup']);
 assert.deepEqual(JSON.stringify(r.calls[2][1]),'{"confirm":true}');
 console.log('V145_ORIGINAL_BROWSER_JS_GUARD_9_9_SOURCE_PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
