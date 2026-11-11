import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {makeOwnerOieDonor,OWNER_BLOB,OIE_BLOB} from '../tools/owner_work_overlay_patch.mjs';

test('no unpinned R78 input is modified',()=>{
 assert.throws(()=>makeOwnerOieDonor('arbitrary owner','arbitrary oie'),/HOLD_R78_BASE_SHA/);
 assert.equal(OWNER_BLOB,'c3c91bae4f22214c0e39d0e1b95e1ccef1205bd4');
 assert.equal(OIE_BLOB,'a74882f14b8f638f1d1c1e2cfb8cc5aa3aa76174');
});
test('exact owner no-loss overlay (only if authorized inputs are present)',()=>{
 const owner=process.env.NOX_R78_OWNER_SOURCE;
 const module=process.env.NOX_OIE_PINNED_SOURCE;
 if(!owner||!module){return; /* Not E07. Independent owner preimages required. */}
 const original=readFileSync(owner,'utf8');
 const originalOie=readFileSync(module,'utf8');
 const applied=makeOwnerOieDonor(original,originalOie);
 assert.equal(applied.packedAssetCount,14);
 assert.equal(applied.release,'HOLD_WINDOWS_E07');
 assert.ok(applied.requiresOwnerNativeOieContract);
 assert.equal((applied.code.match(/if\(selected.id==="W02"/g)||[]).length,1);
 assert.equal((applied.code.match(/function menuWorlds\(/g)||[]).length,1);
 assert.match(applied.code,/HOLD · owner OIE mount failed/);
 assert.doesNotMatch(applied.code,/E07_ACCEPTED|RELEASE_PASS/);
});
