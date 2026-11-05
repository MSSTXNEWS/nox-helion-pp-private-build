// B03 G4: source-only regression, NEVER a physical Windows E07 result.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const read = (p) => readFileSync(new URL("../../"+p,import.meta.url),"utf8");
const builder=read("coordination/e06/build_onehost_installer.ps1");
const canonical=read("stage/proposals/P01/C09/Installer/Remove-InstalledPayload.ps1");
const before="// D03 · A successful NSIS remover exit must not be based solely on\n// Remove-Item returning without an exception. Recheck every manifest-owned\n// leaf BEFORE reporting PASS. A recreated/locked/reparse leaf is a HOLD;\n// read failures other than an exact missing-item exception are also a HOLD.\n// Do not modify retained user files or the NSIS-owned metadata here.";
const after=before.replace(/^\/\//gm,"#");
assert.equal(canonical.split(before).length,2);
assert.equal((canonical.match(/^\/\//gm)||[]).length,5);
assert.equal((after.match(/^#/gm)||[]).length,5);
const staged=canonical.replace(before,after);
assert.equal((staged.match(/^\/\//gm)||[]).length,0);
assert.equal(staged.replace(after,before),canonical);
for(const key of ["P01_UNINSTALL_POST_REMOVE_RESIDUE","P01_UNINSTALL_PAYLOAD_PASS","PHASE 3","Assert-VerifiedEntry"]) {
  assert.ok(staged.includes(key), key);
}
for(const gate of ["B03_P01_PS51_REMOVER_COMMENT_PREIMAGE_HOLD","B03_P01_PS51_REMOVER_COMMENT_TRANSFORM_HOLD","B03_P01_PS51_REMOVER_COMMENT_READBACK_HOLD","B03_P01_PS51_REMOVER_COMMENT_STAGE_PASS"]) {
  assert.ok(builder.includes(gate), gate);
}
assert.ok(builder.indexOf("NX03_C09_REVIEWED_REMOVE_STAGE_PASS")<builder.indexOf("B03_P01_PS51_REMOVER_COMMENT_STAGE_PASS"));
assert.ok(builder.indexOf("B03_P01_PS51_REMOVER_COMMENT_STAGE_PASS")<builder.indexOf("& $makensisPath"));
assert.ok(builder.includes("fed8e70a122118e2e25c6399701d9e7c26434cfe"));
assert.ok(builder.includes("b0107364b70528011a6c2fbcf305556994be573a"));
console.log("B03_PS51_REMOVER_COMMENT_SOURCE_ONLY_PASS");
