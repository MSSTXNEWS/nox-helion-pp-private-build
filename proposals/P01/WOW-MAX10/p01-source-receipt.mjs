/* E01 C7 - actual postimage bytes from Git, never invented readiness. CI only. */
import fs from "node:fs";
import crypto from "node:crypto";
import path from "node:path";
import {fileURLToPath} from "node:url";
import {execFileSync} from "node:child_process";
const BASE="ef10bbba7370f67c734d69dbab8b509d3c2c457e";
const ROOT="proposals/P01/WOW-MAX10/";
const WORKFLOW=".github/workflows/p01-wow-max10.yml";
const sha=bytes=>crypto.createHash("sha256").update(bytes).digest("hex");
const git=(...args)=>execFileSync("git",args,{encoding:"utf8",stdio:["ignore","pipe","pipe"]}).trim();
export function collectReceipt(){
  const head=git("rev-parse","HEAD");
  if(!/^[a-f0-9]{40}$/.test(head)||git("merge-base",BASE,head)!==BASE)
    throw Error("P01_C7_UNEXPECTED_GIT_ANCESTOR");
  const names=git("diff","--name-only",BASE,head).split("\n").filter(Boolean);
  if(names.length<14)throw Error("P01_C7_REQUIRED_OWNER_FILES_MISSING");
  if(names.some(n=>!(n.startsWith(ROOT)||n===WORKFLOW)))
    throw Error("P01_C7_OTHER_OWNER_CHANGED");
  if(git("diff","--diff-filter=D","--name-only",BASE,head))
    throw Error("P01_C7_NO_LOSS_DELETION");
  const rows=[];
  for(const name of names.sort()){
    const bytes=fs.readFileSync(name);
    if(!bytes.length)throw Error("P01_C7_EMPTY_FILE:"+name);
    const diff=execFileSync("git",["diff","--no-ext-diff","--binary",BASE,head,"--",name]);
    if(!diff.length)throw Error("P01_C7_EMPTY_PATCH:"+name);
    const blob=git("rev-parse","HEAD:"+name);
    if(!/^[a-f0-9]{40}$/.test(blob))throw Error("P01_C7_BLOB_IDENTITY");
    rows.push({owner:1,path:name,pre_sha256:"ABSENT",
      post_sha256:sha(bytes),patch_sha256:sha(diff),git_blob_sha1:blob});
  }
  if(rows.filter(r=>r.path.endsWith(".test.mjs")).length<7)
    throw Error("P01_C7_TEST_COVERAGE_MISSING");
  return Object.freeze({schema:"NOX-P01-WOW-MAX10-SOURCE-RECEIPT-v1",
    source_base_sha1:BASE,source_head_sha1:head,generated_utc:new Date().toISOString(),
    rows,deleted_files:0,other_owner_changes:0,
    owner_commit_candidate:true,native_host_integrated:false,
    installed_windows_exe_accepted:false,e07_same_sha_accepted:false,
    release_allowed:false,accepted_product_percent:null});
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const data=collectReceipt();
 fs.mkdirSync("ci-evidence",{recursive:true});
 const dest="ci-evidence/P01_WOW_MAX10_OWNER_RECEIPT.json";
 fs.writeFileSync(dest,JSON.stringify(data,null,2)+"\n",{flag:"w"});
 console.log("P01_OWNER_SOURCE_RECEIPT="+dest+" paths="+data.rows.length+" git="+data.source_head_sha1);
}
