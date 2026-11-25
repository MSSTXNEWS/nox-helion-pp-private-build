'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {stageSnapshot}=require('./stage_snapshot.cjs');
const base=fs.mkdtempSync(path.join(os.tmpdir(),'b3-r89-test-'));
const source=path.resolve(__dirname,'../b3-r88/serving_snapshot.cjs');
const original=fs.readFileSync(source);
let n=0;const test=f=>{f();n++;};
const root=name=>{const r=path.join(base,name);fs.mkdirSync(path.join(r,'nox-control/d3-r114'),{recursive:true});return r;};
const dest=r=>path.join(r,'nox-control/d3-r114/serving_snapshot.cjs');
try{
 test(()=>{const r=root('ok'),sentinel=path.join(path.dirname(dest(r)),'admitted_physical.cjs');fs.writeFileSync(sentinel,'existing');const receipt=stageSnapshot(r);assert.deepEqual(fs.readFileSync(dest(r)),original);assert.equal(fs.readFileSync(sentinel,'utf8'),'existing');assert.equal(receipt.git_blob,'417da2652bbe0d04630d0340478b3ad9b1a15bdd');assert.equal(receipt.native_accepted,false);assert.equal(receipt.ack_allowed,false);const {captureServingIdentity}=require(dest(r));let reads=0;const a={get route_sha256(){reads++;return 'x';}};assert.equal(captureServingIdentity(a),null);assert.equal(reads,0);assert.throws(()=>stageSnapshot(r),/OVERWRITE/);});
 test(()=>{const r=root('tamper');fs.appendFileSync(source,'\n// tamper');try{assert.throws(()=>stageSnapshot(r),/SOURCE_PIN/);assert(!fs.existsSync(dest(r)));}finally{fs.writeFileSync(source,original);}});
 test(()=>{const r=root('symlink'),outside=root('outside');fs.rmdirSync(path.dirname(dest(r)));fs.symlinkSync(path.dirname(dest(outside)),path.dirname(dest(r)),'dir');assert.throws(()=>stageSnapshot(r),/DEST_PATH/);assert(!fs.existsSync(dest(outside)));});
 test(()=>assert.throws(()=>stageSnapshot(path.resolve(__dirname,'../..')),/ROOT/));
 console.log(`${n}/${n} R89 stage cases PASS; synthetic release tree only`);
}finally{fs.rmSync(base,{recursive:true,force:true});}
