// F03 original Windows WPF owner consent ACK semantics · SOURCE_ONLY.
// Not an installed-Windows/NSIS/E07 acceptance or a synthetic native owner.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const root=new URL('../../',import.meta.url);
const read=path=>readFileSync(new URL(path,root),'utf8');
const gitBlob=body=>createHash('sha1').update('blob '+Buffer.byteLength(body)+'\0').update(body).digest('hex');
const sources=[
 ['coordination/e06/OneHostP02WebView2Bridge.cs','field'],
 ['coordination/e06/MainWindow.NativeP02.cs','p']
];
const source={};
for(const [path,variable] of sources){
 const body=read(path);source[path]=body;
 const clause=body.match(new RegExp(variable+'\\.Name is ("ok" or "ack" or "success" or "approved" or "authorized"[^\\n]+?) &&'));
 assert.ok(clause,'original WPF approval guard must be preserved');
 const keys=new Set([...clause[1].matchAll(/"([^"]+)"/g)].map(match=>match[1]));
 for(const key of ['ok','ack','success','approved','authorized','consented','ownerConsent','nativeConsent','permissionGranted'])
   assert.ok(keys.has(key),'native refusal ignored: '+path+' '+key);
 assert.match(body,/GetArrayLength\(\)\s*>\s*128/);
 assert.match(body,/depth\s*>=\s*4/);
}
const builder=read('coordination/e06/build_onehost_installer.ps1');
const compiler=read('coordination/e06/t06_compile_original_wpf_p02.py');
for(const [path] of sources){
 const sha=gitBlob(source[path]);
 assert.ok(builder.includes("'"+sha+"'"),'NSIS stage pin missing '+path);
 assert.ok(compiler.includes('"'+path+'":"'+sha+'"'),'WPF compiler pin missing '+path);
}
console.log('F03_WPF_NATIVE_PERMISSION_DENIAL_CONTRACT SOURCE_ONLY PASS (no Windows physical run)');
