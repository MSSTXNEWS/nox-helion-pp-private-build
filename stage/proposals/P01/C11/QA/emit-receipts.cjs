// E01 C11: derive exact byte receipts from Git objects on the Windows checkout.
"use strict";
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { execFileSync } = require("node:child_process");
const BASE = "10ce423c852396db3149f22e207c5ce614851ea6";
const RUN_ID = "NOX-V16-E01-C12-20261028-NSIS";
const SHA = b => crypto.createHash("sha256").update(b).digest("hex");
const GIT = (args, options={}) => execFileSync("git", args, {maxBuffer: 12*1024*1024, ...options});
const HEAD = GIT(["rev-parse","HEAD"],{encoding:"utf8"}).trim();
const names = ["Build-NSIS.ps1","Get-P01Prerequisites.ps1","Preflight-InstallPath.ps1","Remove-InstalledPayload.ps1","Verify-Payload.ps1","NOX-HELION-Setup.nsi","Test-NSIS-Windows.ps1"];
const files = names.map(name => {
  const file = "stage/proposals/P01/C09/Installer/"+name;
  let before=null;
  try { before=GIT(["show",BASE+":"+file]); } catch(e) {
    // On C12, NSIS .nsi and native transaction test are newly introduced; no preimage.
    if (!["NOX-HELION-Setup.nsi","Test-NSIS-Windows.ps1"].includes(name)) throw e;
  }
  const after=fs.readFileSync(file);
  if (before && before.equals(after)) throw new Error("NO_CHANGE:"+file);
  const patch=GIT(["diff","--binary",BASE,"HEAD","--",file]);
  if (!patch.length) throw new Error("MISSING_DIFF:"+file);
  return {path:file,owner:"E01",run_id:RUN_ID,
    pre_exists:before!==null,
    pre_sha256:before?SHA(before):null,post_sha256:SHA(after),patch_sha256:SHA(patch),
    pre_git_blob_sha1:before?GIT(["hash-object","--stdin"],{input:before,encoding:"utf8"}).trim():null,
    post_git_blob_sha1:GIT(["hash-object","--stdin"],{input:after,encoding:"utf8"}).trim()};
});
const deleted=GIT(["diff","--name-only","--diff-filter=D",BASE,"HEAD"],{encoding:"utf8"}).trim();
if(deleted) throw new Error("NO_LOSS_DELETION:"+deleted);
const changed=GIT(["diff","--name-only",BASE,"HEAD"],{encoding:"utf8"}).trim().split(/\r?\n/).filter(Boolean);
const bad=changed.filter(p=>!p.startsWith("stage/proposals/P01/C09/Installer/") &&
                           !p.startsWith("stage/proposals/P01/C09/QA/") &&
                           !p.startsWith("stage/proposals/P01/C11/") &&
                           p!==".github/workflows/p01-c11-native.yml" &&
                           p!==".github/workflows/p01-c12-nsis-compile.yml");
if (bad.length) throw new Error("FOREIGN_OWNER_FILE_CHANGED:"+bad.join(","));
const out={schema:"NOX_P01_C12_OWNER_SOURCE_RECEIPTS_V2",run_id:RUN_ID,owner:"E01",
 base_commit:BASE,head_commit:HEAD,source_stage:"PR28_SOURCE_CANDIDATE",
 integrated_in_main:false,windows_native_component_verified:"PER_JOB",
 windows_exe_accepted:false,deleted_count:0,source_files:files,changed_paths:changed,
 evidence:"GitHub Windows checkout byte reads, immutable git base commit"};
fs.mkdirSync("ci-evidence",{recursive:true});
const output="ci-evidence/p01-c12-owner-receipts.json";
fs.writeFileSync(output, JSON.stringify(out,null,2)+"\n",{flag:"wx"});
console.log("P01_C11_RECEIPTS_PASS",files.length,"files",changed.length,"paths","sha256",SHA(fs.readFileSync(output)),"head",HEAD);
