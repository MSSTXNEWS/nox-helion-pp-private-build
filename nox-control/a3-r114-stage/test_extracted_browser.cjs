'use strict';
const a=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{createHash}=require('node:crypto');
const {stageBrowser}=require('./stage_browser.cjs');
const root=fs.realpathSync(process.argv[2]),sha=b=>createHash('sha256').update(b).digest('hex');
const snapshot=()=>Object.fromEntries(fs.readdirSync(root,{recursive:true,withFileTypes:true}).filter(x=>x.isFile()).map(x=>{const p=path.join(x.parentPath||x.path,x.name);return [path.relative(root,p),sha(fs.readFileSync(p))];}));
const original=path.join(root,'nox-control/d3-r111/browser/b1_browser_bundle.js'),raw=fs.readFileSync(original);
const before=snapshot();
try{fs.writeFileSync(original,Buffer.concat([raw,Buffer.from('x')]));a.throws(()=>stageBrowser(root),/HOLD_R88_STAGE_PIN/);}
finally{fs.writeFileSync(original,raw);}
a.deepEqual(snapshot(),before);
const selected=stageBrowser(root),after=snapshot();
for(const [p,h] of Object.entries(before))a.equal(after[p],h,p);
a.equal(Object.keys(after).length-Object.keys(before).length,5);
a.throws(()=>stageBrowser(root),/HOLD_R88_STAGE_OVERWRITE/);
a.deepEqual(snapshot(),after);
const consumer=require(selected.consumer);
a.equal(require.resolve(selected.consumer),path.join(root,'nox-control/a3-r113-browser/browser_selection.cjs'));
const bytes=fs.readFileSync(selected.selectedPath);
const pair=o=>{const s=JSON.stringify(o);return [s,sha(s)];};
const make=(browser=selected.browser_sha256)=>({turns:[2,3].map(i=>({observation:pair({observation_id:'obs'+i,browser_sha256:browser,served_sha256:'a'.repeat(64),server_sha256:'b'.repeat(64)})}))});
const packet=JSON.stringify(make());
const route={manifest_sha256:selected.manifest_sha256,successor_role_sha256:selected.role_sha256,assets:{'browser/b1_browser_bundle.js':selected.historical_browser_sha256},browser_sha256:selected.browser_sha256,served_sha256:'a'.repeat(64),server_sha256:'b'.repeat(64),bridge_sha256:'c'.repeat(64),packet_sha256:sha(packet)};
const run=(d,p)=>{const b=Buffer.from(JSON.stringify(d));return consumer.checkSelectedBrowser(b,sha(b),p,bytes);};
const r=run(route,packet);a.equal(r.status,'MATCHED_R88_BROWSER_OFFLINE');
for(const k of ['native_accepted','ack_allowed','authentication_verified','host_provider_bound','next_post_allowed','training_admitted','production_ready'])a.equal(r[k],false);
const bad=make();bad.turns[1].observation=make(selected.historical_browser_sha256).turns[1].observation;
const p=JSON.stringify(bad);a.equal(run({...route,packet_sha256:sha(p)},p).status,'HOLD_R88_OBSERVATION_PIN');
console.log(JSON.stringify({base_unchanged:Object.keys(before).length,added:5,selected_bytes:bytes.length,extracted_consumer:'MATCHED_R88_BROWSER_OFFLINE',mixed_observation:'HOLD',tamper:'HOLD',overwrite:'HOLD',native_accepted:false}));
