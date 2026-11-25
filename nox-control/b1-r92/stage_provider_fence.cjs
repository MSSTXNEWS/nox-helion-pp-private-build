'use strict';
// Candidate only: preserve exact R88/R89 selected release until D3 explicitly repins.
const {createHash}=require('node:crypto');
const {stageR100}=require('../b1-r88/stage_r100.cjs');
const SELECTED='37a756fdc6544f8b5d73425c83221bb958504bd3199dd6245aa4d4b62549651f';
function stageProviderFence(raw){
 const selected=stageR100(raw);
 if(createHash('sha256').update(selected).digest('hex')!==SELECTED)throw Error('HOLD_R92_R88_PIN');
 let src=selected.toString('utf8');
 const replace=(a,b)=>{if(src.split(a).length!==2)throw Error('HOLD_R92_ANCHOR');src=src.replace(a,()=>b);};
 replace("if(!retainedObservation||typeof host.requestFinalDisposition!=='function'||\n                 typeof host.verifyFinalDisposition!=='function')hold('HOLD_R100_PROVIDER');",
 "if(!retainedObservation)hold('HOLD_R100_PROVIDER');\n              const requestFinalDisposition=host.requestFinalDisposition;\n              recheck();\n              if(typeof requestFinalDisposition!=='function')hold('HOLD_R100_PROVIDER');");
 replace("await host.requestFinalDisposition(Object.freeze({scope:s,observation,grant,",
 "await requestFinalDisposition.call(host,Object.freeze({scope:s,observation,grant,");
 replace("if(await host.verifyFinalDisposition(Object.freeze({scope:s,grant,observation:o.fixed,",
 "const verifyFinalDisposition=host.verifyFinalDisposition;\n              recheck();\n              if(typeof verifyFinalDisposition!=='function')hold('HOLD_R100_PROVIDER');\n              if(await verifyFinalDisposition.call(host,Object.freeze({scope:s,grant,observation:o.fixed,");
 return Buffer.from(src,'utf8');
}
module.exports={stageProviderFence};
