/* NOX R78 exact-owner OIE sparse patch. SOURCE ONLY; never merges or builds. */
import { createHash } from 'node:crypto';
export const OWNER_BLOB='c3c91bae4f22214c0e39d0e1b95e1ccef1205bd4';
export const OIE_BLOB='a74882f14b8f638f1d1c1e2cfb8cc5aa3aa76174';
const blob=s=>{const bytes=Buffer.from(s,'utf8');return createHash('sha1').update(Buffer.from('blob '+bytes.length+'\0')).update(bytes).digest('hex')};
const single=(s,x)=>s.split(x).length===2;
export function makeOwnerOieDonor(owner,oie){
 if(typeof owner!=='string'||blob(owner)!==OWNER_BLOB)throw Error('HOLD_R78_BASE_SHA');
 if(typeof oie!=='string'||blob(oie)!==OIE_BLOB)throw Error('HOLD_OIE_SOURCE_SHA');
 const A='function workViews(control,s,store,probe){';
 const R='function render(){\n  if(closed)return;\n  body.replaceChildren(node("h3",selected.label));';
 const D='  body.append(observed);';
 const C='return {element:panel,destroy(){closed=true;unsubscribe();panel.remove()}};';
 if(![A,R,D,C].every(x=>single(owner,x))||!single(oie,'export function mountOpportunityPanel'))throw Error('HOLD_R78_ANCHORS');
 const embedded=oie.replace('export function mountOpportunityPanel','function mountOpportunityPanel');
 const addon=[
  '  // Existing W02 PROJECTS only: no new menu, host or extra assets.',
  '  if(selected.id==="W02" && typeof window.chrome?.webview?.noxOwnerOieRequestJob==="function"){',
  '    const slot=node("section",undefined,"mega814-oie-slot");',
  '    slot.dataset.noxScreen="opportunity-engine";body.append(slot);',
  '    try{oieHandle=mountOpportunityPanel(slot,{apiBase:"",',
  '      onBack:()=>{const original=document.querySelector(\'#tiles [data-menu-index="0"]\');if(original&&!original.disabled)original.click();},',
  '      requestJob:window.chrome.webview.noxOwnerOieRequestJob.bind(window.chrome.webview)',
  '    });}catch{note(body,"HOLD · owner OIE mount failed");}',
  '  }',
 ].join('\n');
 const x=[
   [A,embedded+'\n'+A+'\n let oieHandle=null;'],
   [R,'function render(){\n  if(closed)return;\n  oieHandle?.dispose();oieHandle=null;\n  body.replaceChildren(node("h3",selected.label));'],
   [D,D+'\n'+addon],
   [C,'return {element:panel,destroy(){closed=true;oieHandle?.dispose();unsubscribe();panel.remove()}};'],
 ];
 let output=owner;
 for(const [from,to] of x)output=output.replace(from,to);
 let reverse=output;for(const [from,to] of x.slice().reverse())reverse=reverse.replace(to,from);
 if(reverse!==owner)throw Error('HOLD_OWNER_NOLOSS');
 return Object.freeze({code:output,sourceBlob:OWNER_BLOB,resultBlob:blob(output),
   packedAssetCount:14,release:'HOLD_WINDOWS_E07',requiresOwnerNativeOieContract:true});
}
