/** WEB V29 source-locked preview from the ONE verified 1053-file sandbox payload.
 * Only a staging build. This never touches production/Windows/S03/weights.
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import os from 'node:os';
import {execFileSync} from 'node:child_process';

const sourceUrl = 'https://sb-ow5ftc09y8ww.vercel.run/NOX_V29_SITE_PAYLOAD.tar.gz';
const expectedArchive = '3319c26b3600b4a20a3aaf3a92d240b7c87cc80dffab11d4ce42a3f0d7014b3c';
const sourceV29 = '1481e26f8f0e2febf80d773a78557094fb6ee91d8d7f39a70374855dde0570f1';
const manifestSha = '8d7041db6784e98825c8eace42dad6c863270728247be7b47d2b3ab9a0267d60';
const output = path.join(process.cwd(), 'web_v29_preview_dist');
if (fs.existsSync(output)) throw Error('NOX_NO_OVERWRITE_EXISTING_DIST');
fs.mkdirSync(output, {recursive:true});
const tmp = path.join(os.tmpdir(),'nox-v29-source-pinned-'+process.pid+'.tar.gz');
const digest = crypto.createHash('sha256');
let bytes = 0;
try {
  const url = new URL(sourceUrl);
  if (url.protocol!=='https:' || url.hostname!=='sb-ow5ftc09y8ww.vercel.run' || url.pathname!=='/NOX_V29_SITE_PAYLOAD.tar.gz') throw Error('UNTRUSTED_SOURCE_URL');
  const response = await fetch(url,{redirect:'error',signal:AbortSignal.timeout(180_000)});
  if (response.status!==200 || !response.body) throw Error('NOX_SOURCE_READ_HOLD_'+response.status);
  const fd = fs.openSync(tmp,'wx');
  try {
    for await (const chunk of response.body) {
      bytes+=chunk.length;
      if (bytes>82_000_000) throw Error('NOX_MAXIMUM_PAYLOAD_EXCEEDED');
      fs.writeSync(fd,chunk); digest.update(chunk);
    }
  } finally {fs.closeSync(fd)}
  const sourceHash=digest.digest('hex');
  if(sourceHash!==expectedArchive || bytes!==79_765_326) throw Error('NOX_SOURCE_SHA256_HOLD:'+sourceHash+':'+bytes);
  const paths=execFileSync('tar',['-tzf',tmp],{encoding:'utf8',maxBuffer:2*1024*1024}).trim().split('\n');
  if(paths.length!==1053 || paths.some(p=>!p||p.startsWith('/')||p.split('/').some(s=>s==='..'||s==='.'||s==='')))throw Error('NOX_TAR_UNSAFE_OR_INCOMPLETE');
  execFileSync('tar',['-xzf',tmp,'-C',output],{timeout:100_000});
  const sha=f=>crypto.createHash('sha256').update(fs.readFileSync(path.join(output,f))).digest('hex');
  for (const [file, expected] of Object.entries({
    'index.html':'f3fc804d238146ffe42c50103d3e04c9736b8b587c6572987f59b61a6112eb17',
    'nox-home.mjs':'8066bc0a0f8ef5bb5f0fb1f58ad3f6ee29dc8506385c09d77d38d4235c7e42e9',
    'nox-engines/physical-worlds-v7.mjs':'3f27609ea37b96579a711928e4c67778ec71e2ff7b090a3b7bb41e29040f3905',
    'nox-chat.js':'d9fa29e0fa726502adc6e83ea344adf13b8a2354acd3610b3de96ec378e942ce',
    'nox-function-catalog.js':'c509870d8fc664bb7c60cd53d3daf21280aa410832d978d3fedbd0543730f661'
  })) if(sha(file)!==expected)throw Error('NOX_PRIMARY_SOURCE_DRIFT:'+file);
  const r=JSON.parse(fs.readFileSync(path.join(output,'NOX_V29_STATIC_PREVIEW_RECEIPT.json'),'utf8'));
  if(r.schema!=='NOX_WEB_V29_STATIC_BUNDLE_CHECKSUM_V1'||r.source_build_sha256!==sourceV29||r.file_digest_manifest_sha256!==manifestSha||r.files!==1052) throw Error('NOX_RECEIPT_MISMATCH');
  for (const p of ['index','chat','memory','training','models','settings','system','projects','cinema','install']) if(!fs.existsSync(path.join(output,p+'.html')))throw Error('NOX_MISSING_PAGE:'+p);
  for (const p of ['pc/resonance.html','pc/memory.html','nox-v29-pc-genesis-addons.mjs','nox-v29-pc-genesis-addons.css']) if(!fs.existsSync(path.join(output,p)))throw Error('NOX_MISSING_ADDON:'+p);
  console.log('NOX_WEB_V29_VERIFIED_PREVIEW_BUILD',JSON.stringify({sourceV29,sourceHash,bytes,files:paths.length,primaryD02:'SHA256_PASS',allTenPages:true,pcAddon:true,nativeOneHost:'HOLD',productionModified:false}));
} catch(e) {
  fs.rmSync(output,{recursive:true,force:true});
  throw e;
} finally {
  fs.rmSync(tmp,{force:true});
}
