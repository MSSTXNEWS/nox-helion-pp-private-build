'use strict';
// Offline additive stage only; D3 owns the joint callsite and native admission.
const fs=require('node:fs'),path=require('node:path'),{createHash}=require('node:crypto');
const repo=path.resolve(__dirname,'../..');
const blob=b=>createHash('sha1').update(Buffer.from('blob '+b.length+'\0')).update(b).digest('hex');
const sha=b=>createHash('sha256').update(b).digest('hex');
const pin='417da2652bbe0d04630d0340478b3ad9b1a15bdd';
const source='nox-control/b3-r88/serving_snapshot.cjs';
const destination='nox-control/d3-r114/serving_snapshot.cjs';
function stageSnapshot(target){
 const root=fs.realpathSync(target);
 if(root===repo||root.startsWith(repo+path.sep)||repo.startsWith(root+path.sep))throw Error('HOLD_R89_ROOT');
 const src=path.join(repo,source),f=path.join(root,destination),dir=path.dirname(f);
 if(fs.realpathSync(src)!==src||!fs.statSync(src).isFile())throw Error('HOLD_R89_SOURCE_PATH');
 const raw=fs.readFileSync(src);
 if(blob(raw)!==pin)throw Error('HOLD_R89_SOURCE_PIN');
 if(fs.realpathSync(dir)!==dir||!fs.statSync(dir).isDirectory())throw Error('HOLD_R89_DEST_PATH');
 if(fs.lstatSync(f,{throwIfNoEntry:false}))throw Error('HOLD_R89_OVERWRITE');
 fs.writeFileSync(f,raw,{flag:'wx'});
 if(blob(fs.readFileSync(f))!==pin)throw Error('HOLD_R89_POSTIMAGE');
 return Object.freeze({path:destination,git_blob:pin,sha256:sha(raw),native_accepted:false,authentication_verified:false,host_provider_bound:false,production_ready:false,ack_allowed:false,next_post_allowed:false,training_admitted:false});
}
module.exports={stageSnapshot};
