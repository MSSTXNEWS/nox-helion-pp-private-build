/* NOX V16 W2.03 R17: independent D02 owner/publisher pin-graph QA.
 * No production writes, no assets substituted, no native Windows PASS.
 * A red owner pin is an actionable SOURCE staging blocker.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {dirname,resolve,join} from 'node:path';
import {fileURLToPath} from 'node:url';

const repo=resolve(dirname(fileURLToPath(import.meta.url)),'../../..');
const sourcePath='integrations/wow200/stage_wow200.py';
const builderPath='coordination/e06/build_onehost_installer.ps1';
const stage=readFileSync(join(repo,sourcePath),'utf8');
const builder=readFileSync(join(repo,builderPath),'utf8');
const home=readFileSync(join(repo,'integrations/wow200/runtime/home-scene.mjs'),'utf8');
const activeBase='proposals/NOX-CINEMA-FX/';
const donorBase='integrations/wow200/proposals/NOX-CINEMA-FX/';

function blob(bytes){
  return createHash('sha1').update('blob '+bytes.length+'\0').update(bytes).digest('hex');
}
function fileBlob(rel){return blob(readFileSync(join(repo,rel)));}
function pinned(name){
  const marker='"'+activeBase+name+'"';
  const offset=stage.indexOf(marker);
  assert.notEqual(offset,-1,'no canonical owner pin for '+name);
  const block=stage.slice(offset,offset+220);
  const active=block.match(/"active_blob"\s*:\s*"([0-9a-f]{40})"/);
  const legacy=block.match(/"legacy_blob"\s*:\s*"([0-9a-f]{40})"/);
  assert.ok(active&&legacy,'incomplete dual pin for '+name);
  return {active:active[1],legacy:legacy[1]};
}
function ownerBlob(name){return fileBlob(activeBase+name);}

test('R17-01 owner .mjs blob equals immutable staging active pin',()=>{
  assert.equal(ownerBlob('nox-cinema.mjs'),pinned('nox-cinema.mjs').active,
    'OWNER1_D02_ENGINE_SHA_HOLD: owner changed, stage pin must be reapproved');
});
test('R17-02 owner CSS blob equals immutable staging active pin',()=>{
  assert.equal(ownerBlob('nox-cinema.css'),pinned('nox-cinema.css').active);
});
test('R17-03 untouched donor blobs remain immutable and distinct',()=>{
  for(const name of ['nox-cinema.mjs','nox-cinema.css']){
    assert.equal(fileBlob(donorBase+name),pinned(name).legacy);
    assert.notEqual(fileBlob(donorBase+name),ownerBlob(name));
  }
});
test('R17-04 HOME import and staging map resolve to owner active payload',()=>{
  assert.match(home,/from '\.\.\/proposals\/NOX-CINEMA-FX\/nox-cinema\.mjs'/);
  assert.match(stage,/plans\.append\(\(origin,dest\/"legacy\/d02-pr30"\/Path\(rel\)\.name\)\)/);
  assert.match(stage,/plans\.append\(\(owner1_root\/rel,dest\/rel\)\)/);
});
test('R17-05 builder pins the unchanged canonical stage script blob',()=>{
  assert.ok(builder.includes("$wowScriptBlob -cne '"+blob(Buffer.from(stage,'utf8'))+"'"));
});
test('R17-06 isolated pin repair exposes downstream builder pin dependency',()=>{
  const old=pinned('nox-cinema.mjs').active;
  const current=ownerBlob('nox-cinema.mjs');
  const candidate=stage.replace('"active_blob": "'+old+'"',
    '"active_blob": "'+current+'"');
  assert.ok(candidate.includes('"active_blob": "'+current+'"'));
  if(current!==old){
    assert.notEqual(blob(Buffer.from(candidate,'utf8')),blob(Buffer.from(stage,'utf8')),
      'changed stage script must be re-pinned in builder by its owner');
    assert.equal(pinned('nox-cinema.css').active,ownerBlob('nox-cinema.css'));
  }else assert.equal(candidate,stage);
});
