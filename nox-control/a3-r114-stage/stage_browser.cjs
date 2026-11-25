'use strict';
// Offline extraction only. Preserve historical R86; select R88 exactly once.
const fs=require('node:fs'),path=require('node:path'),{createHash}=require('node:crypto');
const repo=path.resolve(__dirname,'../..');
const sha=b=>createHash('sha256').update(b).digest('hex');
const blob=b=>createHash('sha1').update(Buffer.from('blob '+b.length+'\0')).update(b).digest('hex');
const PINS={
 'nox-control/d3-r111/browser/b1_browser_bundle.js':'bd2e154fd2c6007cb315d310e109de470f54f72f',
 'nox-control/d3-r111/bridge/b3_r64_eof_candidate.js':'66595eac01c562aff4daae68f5d146aaed64cbbe',
 'nox-control/d3-r111/inputs/b1.json':'3de1fd004cfd76ca17cf7a83dabd7036fb874a38',
 'nox-control/d3-r111/inputs/b3.json':'3f9e77a561c6bb970f5482322bd62a8c2dfe8b25'
};
const DONORS={
 'nox-control/d3-r111/release.json':'fd6b4dd58465de1b7874c36f292acd98be7bb6c5',
 'nox-control/a3-r113-browser/browser_role_input.json':'a3c10fa7ee627d3f5d7517e55f36d8f68005b1e4',
 'nox-control/a3-r113-browser/stage_r100.cjs':'157270b88577fc0c4a92bf45f07f041ef89b1251',
 'nox-control/a3-r113-browser/browser_selection.cjs':'452e8b58b5b9c8559e72ea23f5f2447eb3a3ce71'
};
const selectedPath='nox-control/d3-r111-successor/browser/b1_browser_r100.js';
function exact(root,p,pin){
 const f=path.join(root,p);
 if(fs.realpathSync(f)!==f||!fs.statSync(f).isFile())throw Error('HOLD_R88_STAGE_PATH');
 const raw=fs.readFileSync(f);
 if(blob(raw)!==pin)throw Error('HOLD_R88_STAGE_PIN');
 return raw;
}
function stageBrowser(target){
 const root=fs.realpathSync(target);
 if(root===repo||root.startsWith(repo+path.sep)||repo.startsWith(root+path.sep))throw Error('HOLD_R88_STAGE_ROOT');
 for(const [p,pin] of Object.entries(PINS))exact(root,p,pin);
 const additions=Object.entries(DONORS).map(([p,pin])=>[p,exact(repo,p,pin)]);
 for(const p of [...additions.map(x=>x[0]),selectedPath]){
  const f=path.join(root,p);
  if(fs.existsSync(f)||fs.lstatSync(f,{throwIfNoEntry:false}))throw Error('HOLD_R88_STAGE_OVERWRITE');
  let parent=path.dirname(f);
  while(!fs.existsSync(parent))parent=path.dirname(parent);
  if(fs.realpathSync(parent)!==parent||!fs.statSync(parent).isDirectory())throw Error('HOLD_R88_STAGE_PATH');
 }
 const written=[];
 const write=(p,raw)=>{
  const f=path.join(root,p);fs.mkdirSync(path.dirname(f),{recursive:true});
  if(fs.realpathSync(path.dirname(f))!==path.dirname(f))throw Error('HOLD_R88_STAGE_PATH');
  fs.writeFileSync(f,raw,{flag:'wx'});written.push(f);
 };
 try{
  for(const [p,raw] of additions)write(p,raw);
  const consumer=path.join(root,'nox-control/a3-r113-browser/browser_selection.cjs');
  const selected=require(consumer).stageSelectedBrowser();
  if(selected.bytes.length!==89135||sha(selected.bytes)!=='37a756fdc6544f8b5d73425c83221bb958504bd3199dd6245aa4d4b62549651f')throw Error('HOLD_R88_STAGE_SELECTED');
  write(selectedPath,selected.bytes);
  return Object.freeze({consumer,selectedPath:path.join(root,selectedPath),browser_sha256:selected.browser_sha256,role_sha256:selected.role_sha256,manifest_sha256:selected.manifest_sha256,historical_browser_sha256:selected.historical_browser_sha256,native_accepted:false,ack_allowed:false});
 }catch(e){for(const f of written.reverse())fs.unlinkSync(f);throw e;}
}
module.exports={stageBrowser};
