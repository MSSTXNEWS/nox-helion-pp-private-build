'use strict';
// G2-C / G3-B: source-only negative regression. Node: node tests/P03/test_g2c_g3b_ui_evidence_r23.cjs
function verify(source, UrlCtor) {
  const byId = {};
  function node(tag) {
    return {tagName:tag||'DIV',children:[],textContent:'',value:'',checked:false,disabled:false,hidden:true,
      classList:{add(){},toggle(){}},style:{setProperty(){}},append(...x){this.children.push(...x)},
      replaceChildren(...x){this.children=x},addEventListener(){},setAttribute(){},removeAttribute(){}};
  }
  const document = {getElementById(id){return byId[id]||(byId[id]=node());},createElement:node,
    querySelectorAll(){return []},addEventListener(){},activeElement:null};
  const sent=[],window={chrome:{webview:{postMessage(x){sent.push(x)},addEventListener(){}}}};
  const app = new Function('document','window','URL','setTimeout','clearTimeout', source+
    ';return {state,hasEvidence,renderHero,sendAction,processMessage};')(
    document,window,UrlCtor,()=>0,()=>{});
  const good={id:'llama3.1',name:'Llama 3.1',officialUrl:'https://ollama.com/library/llama3.1',
    artifactVerified:true,exactTag:'llama3.1:8b',immutableRevision:'f'.repeat(64),
    license:'Apache-2.0',licenseEvidenceUrl:'https://example.org/license',artifactBytes:2000000000,
    sha256:'1'.repeat(64),manifestSha256:'2'.repeat(64),requiredVramGiB:4,compatibilityReviewed:true};
  const checks=[];
  function check(name,condition){checks.push({name,pass:condition===true});}
  function load(m){
    app.state.models=[m];app.state.activeId=m.id;app.state.hostReady=true;
    app.state.capabilities={pull:true,stop:true,retry:true};app.state.activeJob=null;
    app.state.pending.clear();document.getElementById('licenseAck').checked=true;app.renderHero();
  }
  load(good);
  check('valid native-style pin enables UI pull',app.hasEvidence(good)===true&&!document.getElementById('pullBtn').disabled);
  for(const [name,delta] of [
    ['object tag',{exactTag:{value:'llama3.1:8b'}}],
    ['latest tag',{exactTag:'llama3.1:latest'}],
    ['object revision',{immutableRevision:{key:'x'}}],
    ['HTTP license URL',{licenseEvidenceUrl:'http://example.org/license'}],
    ['localhost license URL',{licenseEvidenceUrl:'https://localhost/license'}],
    ['mismatched official family',{officialUrl:'https://ollama.com/library/another'}],
    ['all-zero digest',{manifestSha256:'0'.repeat(64)}],
    ['object license',{license:{text:'Apache'}}]
  ])check('unreviewed '+name+' denied',app.hasEvidence(Object.assign({},good,delta))===false);
  load(good);const before=sent.length;document.getElementById('licenseAck').checked=false;
  app.sendAction('pull');check('no consent no pull',sent.length===before);
  load(Object.assign({},good,{artifactVerified:false}));
  const jid='01234567-89ab-cdef-0123-456789abcdef';
  app.state.activeJob={jobId:jid,modelTag:'custom-gguf:one',state:'Running',completedBytes:5,totalBytes:10};
  app.renderHero();check('orphan GGUF STOP available',document.getElementById('stopBtn').disabled===false);
  app.sendAction('stop');check('STOP durable jobId',sent.at(-1)?.action==='stop'&&sent.at(-1)?.jobId===jid);
  app.processMessage({type:'p03.event.v1',event:{jobId:jid,modelTag:'custom-gguf:one',phase:'cancelled',status:'Cancelled'}});
  check('cancel confirmation',app.state.activeJob?.state==='Cancelled');
  app.renderHero();check('orphan GGUF retry available',document.getElementById('retryBtn').disabled===false);
  app.sendAction('retry');check('retry durable jobId',sent.at(-1)?.action==='retry'&&sent.at(-1)?.jobId===jid);
  return {passed:checks.filter(x=>x.pass).length,total:checks.length,failures:checks.filter(x=>!x.pass)};
}
module.exports={verify};
if(require.main===module){
  const fs=require('node:fs'),path=require('node:path');
  const file=path.resolve(__dirname,'../../Packages/P03/Source/P03.ModelCenter.Wow/ui.js');
  const result=verify(fs.readFileSync(file,'utf8'),URL);
  console.log(JSON.stringify(result));
  if(result.passed!==result.total)process.exitCode=1;
}