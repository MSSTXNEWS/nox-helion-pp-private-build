'use strict';
// G2-C/G3-B regression: changed P03 native snapshot evidence must invalidate old user consent.
// Run: node tests/P03/test_g2c_g3b_consent_snapshot_r24.cjs
function verify(source, UrlCtor) {
  const nodes={};
  function node(tag){return {tagName:tag||'div',value:'',textContent:'',checked:false,hidden:true,disabled:false,dataset:{},children:[],
    classList:{add(){},toggle(){}},style:{setProperty(){}},append(...x){this.children.push(...x)},
    replaceChildren(...x){this.children=x},addEventListener(){},setAttribute(){},removeAttribute(){}}}
  const document={getElementById(id){return nodes[id]||(nodes[id]=node())},createElement:node,querySelectorAll(){return []},addEventListener(){}};
  const sent=[],window={chrome:{webview:{postMessage(x){sent.push(x)},addEventListener(){}}}};
  const app=new Function('document','window','URL','setTimeout','clearTimeout',
    source+';return {state,processMessage,sendAction,hasEvidence};')(
    document,window,UrlCtor,()=>0,()=>{});
  const base={id:'llama3.1',name:'Llama',officialUrl:'https://ollama.com/library/llama3.1',
    artifactVerified:true,exactTag:'llama3.1:8b',immutableRevision:'f'.repeat(64),
    license:'Apache-2.0',licenseEvidenceUrl:'https://example.org/old',artifactBytes:2000000000,
    sha256:'1'.repeat(64),manifestSha256:'2'.repeat(64),requiredVramGiB:4,
    recommendedRamGiB:8,requiredDiskGiB:3,compatibilityReviewed:true};
  const cases=[
    ['unchanged',{},true],['license',{license:'MIT'},false],
    ['license evidence URL',{licenseEvidenceUrl:'https://example.org/new'},false],
    ['official family URL',{officialUrl:'https://ollama.com/library/llama3.1?new=1'},false],
    ['artifact bytes',{artifactBytes:2000000001},false],
    ['disk',{requiredDiskGiB:5},false],['vram',{requiredVramGiB:6},false],
    ['ram',{recommendedRamGiB:10},false],
    ['compatibility verdict',{compatibilityReviewed:false},false],
    ['artifact verdict',{artifactVerified:false},false],
    ['name only',{name:'New name'},true]];
  const checks=[];
  for(const [name,delta,expectAck] of cases){
    app.state.models=[{...base}];app.state.activeId=base.id;app.state.hostReady=true;
    app.state.activeJob=null;app.state.pending.clear();
    app.state.capabilities={pull:true,stop:true,retry:true,importGguf:true};
    document.getElementById('licenseAck').checked=true;
    app.processMessage({type:'p03.snapshot.v1',models:[{...base,...delta}],activeJob:null,
      capabilities:app.state.capabilities});
    checks.push({name,pass:document.getElementById('licenseAck').checked===expectAck});
    if(name==='license evidence URL'){
      const before=sent.length;app.sendAction('pull');
      checks.push({name:'changed license evidence cannot reuse old pull consent',
        pass:sent.length===before});
    }
  }
  return {passed:checks.filter(x=>x.pass).length,total:checks.length,
    failed:checks.filter(x=>!x.pass).map(x=>x.name)};
}
module.exports={verify};
if(require.main===module){
  const fs=require('node:fs'),path=require('node:path');
  const file=path.resolve(__dirname,'../../Packages/P03/Source/P03.ModelCenter.Wow/ui.js');
  const out=verify(fs.readFileSync(file,'utf8'),URL);
  console.log(JSON.stringify(out));
  if(out.passed!==out.total)process.exitCode=1;
}
