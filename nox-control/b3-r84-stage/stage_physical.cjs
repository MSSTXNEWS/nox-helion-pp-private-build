'use strict';
// B3 offline staging: exact R83 consumer; D3 retains the joint callsite.
const fs=require('node:fs'),path=require('node:path'),{createHash}=require('node:crypto');
const repo=path.resolve(__dirname,'../..');
const hash=b=>createHash('sha256').update(b).digest('hex');
const blob=b=>createHash('sha1').update(Buffer.from('blob '+b.length+'\0')).update(b).digest('hex');
const pins={
 'nox-control/d3-r111/bridge/b3_r64_eof_candidate.js':'66595eac01c562aff4daae68f5d146aaed64cbbe',
 'nox-control/d3-r111/inputs/b3.json':'3f9e77a561c6bb970f5482322bd62a8c2dfe8b25'
};
const source='coordination/onepass/b3_r83_admitted_physical.cjs',pin='a0c5fb3a7770af48d69e8e2382ce1c94d0137ba7';
const destination='nox-control/d3-r114/admitted_physical.cjs';
function exact(root,p,expected){
 const f=path.join(root,p);
 if(fs.realpathSync(f)!==f||!fs.statSync(f).isFile())throw Error('HOLD_B3_STAGE_PATH');
 const b=fs.readFileSync(f);
 if(blob(b)!==expected)throw Error('HOLD_B3_STAGE_PIN');
 return b;
}
function stagePhysical(target){
 const root=fs.realpathSync(target);
 if(root===repo||root.startsWith(repo+path.sep)||repo.startsWith(root+path.sep))throw Error('HOLD_B3_STAGE_ROOT');
 for(const [p,b] of Object.entries(pins))exact(root,p,b);
 if(hash(exact(root,Object.keys(pins)[0],Object.values(pins)[0]))!=='c44b5aa2ef3d45246276a24bbcfad30bf76533fc2e08089eb91b442002643dc7')throw Error('HOLD_B3_STAGE_BRIDGE');
 const raw=exact(repo,source,pin),f=path.join(root,destination);
 if(fs.lstatSync(f,{throwIfNoEntry:false}))throw Error('HOLD_B3_STAGE_OVERWRITE');
 let dir=path.dirname(f);
 while(!fs.lstatSync(dir,{throwIfNoEntry:false}))dir=path.dirname(dir);
 if(fs.realpathSync(dir)!==dir||!fs.statSync(dir).isDirectory())throw Error('HOLD_B3_STAGE_PATH');
 fs.mkdirSync(path.dirname(f),{recursive:true});
 if(fs.realpathSync(path.dirname(f))!==path.dirname(f))throw Error('HOLD_B3_STAGE_PATH');
 fs.writeFileSync(f,raw,{flag:'wx'});
 if(blob(fs.readFileSync(f))!==pin){fs.unlinkSync(f);throw Error('HOLD_B3_STAGE_POSTIMAGE');}
 return Object.freeze({consumer:f,git_blob:pin,sha256:hash(raw),native_accepted:false,authentication_verified:false,host_provider_bound:false,ack_allowed:false,next_post_allowed:false,training_admitted:false,production_ready:false});
}
module.exports={stagePhysical};
