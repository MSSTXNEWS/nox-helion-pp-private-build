/* Exact V27 QA: real WEB catalog source and unchanged original D02/PBR.
   Source checks only; browser click tests are separate and never claim OneHost. */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import crypto from 'node:crypto';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../dist');
const text=f=>fs.readFileSync(path.join(root,f),'utf8');
const sha=f=>crypto.createHash('sha256').update(fs.readFileSync(path.join(root,f))).digest('hex');
test('original owner D02 and 14-PBR physics are byte-for-byte identical',()=>{
 assert.equal(sha('nox-home.mjs'),'8066bc0a0f8ef5bb5f0fb1f58ad3f6ee29dc8506385c09d77d38d4235c7e42e9');
 assert.equal(sha('nox-engines/physical-worlds-v7.mjs'),'3f27609ea37b96579a711928e4c67778ec71e2ff7b090a3b7bb41e29040f3905');
});
test('V27 catalog output has exactly the SHA-pinned postimages',()=>{
 assert.equal(sha('nox-function-catalog.js'),'c509870d8fc664bb7c60cd53d3daf21280aa410832d978d3fedbd0543730f661');
 assert.equal(sha('nox-function-catalog.css'),'c2059ad63829f82b171d2f2e776ee0137b1402fc2f26b96d02b3e3c9eff37605');
});
test('public catalog cannot advertise native-only session and events as live',()=>{
 const js=text('nox-function-catalog.js');
 for(const term of ["nativeOnlyPublic=new Set(['session','events'])","a.disabled=true","HOLD_NATIVE_ONLY","NOX_NATIVE_OWNER===true"])
  assert.ok(js.includes(term),'No-native-live gate missing '+term);
 assert.ok(js.includes("if(native){grid.append(a);continue;}"),'Trusted owner route shape changed');
});
test('favorites and recent operations persist route identifiers only, not chats or S03',()=>{
 const js=text('nox-function-catalog.js');
 for(const term of ['nox.web.ui.favorite.ids.v1','nox.web.ui.recent.ids.v1','validIds.has(v)','storeIds(favoritesKey,[...favorites])','recordRecent(item.id)','catalogView===','nox-function-favorite'])
   assert.ok(js.includes(term),'Favorites source missing '+term);
 assert.ok(js.includes("item.id==='commands'")&&js.includes("item.id==='favorites'"),'Command/favorites source routing absent');
});
test('no additional blank top-level page or placeholder backend was introduced',()=>{
 const js=text('nox-function-catalog.js');
 assert.doesNotMatch(js,/fetch\(|XMLHttpRequest|new WebSocket|model.*pull|\/api\/nox\/stop/);
 for(const name of ['index','chat','training','models','memory','system','projects','install','cinema','settings'])
   assert.ok(fs.existsSync(path.join(root,name+'.html')),'Missing original '+name);
});
