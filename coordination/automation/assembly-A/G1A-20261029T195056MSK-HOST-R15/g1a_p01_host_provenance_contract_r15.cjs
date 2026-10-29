"use strict";
// G1-A scoped read-only contract probe. NO product source writes, build or installation.
// Accepts a pinned Git tree, never an unverified mutable checkout.
// Returns audit PASS for proving the gap, but P01 acceptance remains HOLD.
const BASE = Object.freeze({
 head:"23c1557c0347fa0b66a7cd8d92a4a76637861402",tree:"4dc3325a52b6cfc863e29dd565c758210c059a88",
 bridge:"6338c56c509c31d8deee70afef6eb639603e1e2d",
 builder:"ca8ce5d046452d8f2ad0730293171da3f9797f85",
 p02:"8af1338bee7ebb03ffbb0dd4bfdeed7af7870bc1",
 p03catalog:"72e72960b69c74cd9d11cdc5fa0c6eebee6aefcf",
 p03queue:"3692811ac3234afb54e82958c7415b23619c1f0f"
});
function inspect(s){
  const paths=new Map(s.tree.map(r=>[r.path,r.sha]));
  const has=p=>paths.has(p),get=p=>paths.get(p);
  const tests={
    tree_pinned:s.treeSha===BASE.tree && s.truncated===false,
    candidate_bridge_pinned:get("stage/proposals/P01/C09/Bridge/P01WebView2NavigationBridge.cs")===BASE.bridge,
    candidate_requires_existing_host:s.bridge.includes("Adapter for the EXISTING WPF WebView2 host"),
    consent_and_origin_guard:s.bridge.includes("confirmNativeConsent") && s.bridge.includes("P01_TRUSTED_WEBVIEW2_VIRTUAL_ORIGIN_REQUIRED") && s.bridge.includes("NewWindowRequested"),
    builder_pinned:get("coordination/e06/build_onehost_installer.ps1")===BASE.builder,
    builder_requires_original_project:s.builder.includes("$project=Join-Path $source 'NOX.P01.Shell.csproj'") && s.builder.includes("EXISTING_WPF_SOURCE_MISSING"),
    project_absent_in_pinned_git:![...paths.keys()].some(p=>p.endsWith("NOX.P01.Shell.csproj")),
    mainwindow_absent_in_pinned_git:![...paths.keys()].some(p=>/MainWindow\.xaml(?:\.cs)?$/.test(p)),
    p02_framed_is_already_present:get("Packages/P02/worker-python/p02_framed_worker.py")===BASE.p02,
    p03_catalog_is_already_present:get("Packages/P03/Source/P03.ModelCenter/ModelCatalog.cs")===BASE.p03catalog,
    p03_queue_is_already_present:get("Packages/P03/Source/P03.ModelCenter/ModelDownloadQueueWorker.cs")===BASE.p03queue,
    t06_r15_nsis_guard_present:has("tests/e06/test_t06_p01_nsis_powershell_contract_r15.py"),
    original_host50_13_holds_unchanged:s.ledger.rows.filter(r=>r.SOURCE==="HOLD").length===13
  };
  const failure=Object.entries(tests).filter(([k,v])=>!v).map(([k])=>k);
  return {audit_pass:failure.length===0,checks:Object.keys(tests).length,passed:Object.keys(tests).length-failure.length,failed:failure,
    source_p01_accepted:false,source_p02_p03_not_reaccepted:true,status:failure.length?"AUDIT_BLOCKED":"P01_EXISTING_WPF_HOST_PROVENANCE_HOLD",
    required_owner:"T06/manual №1",next_action:"Provide exact owner-approved original WPF csproj/MainWindow/Pack01HostBridge from a preserved non-ZIP729 source, pin Git PRE/POST and prove C09 binding to ONE host; same-SHA independent QA."};
}
if(typeof module!=="undefined"&&module.exports){
  module.exports={inspect};
  if(typeof require!=="undefined"&&require.main===module){
    const cp=require("node:child_process");const fs=require("node:fs");
    const run=args=>cp.execFileSync("git",args,{encoding:"utf8",maxBuffer:16*1024*1024});
    const raw=run(["ls-tree","-r","-z",BASE.head]);
    const tree=raw.split("\0").filter(Boolean).map(row=>{const [meta,path]=row.split("\t");return {path,sha:meta.split(" ")[2]}});
    const read=p=>run(["show",BASE.head+":"+p]);
    const s={tree,treeSha:BASE.tree,truncated:false,
      bridge:read("stage/proposals/P01/C09/Bridge/P01WebView2NavigationBridge.cs"),
      builder:read("coordination/e06/build_onehost_installer.ps1"),
      ledger:JSON.parse(read("coordination/e06_host50/CURRENT_50_TASK_LEDGER.json"))};
    const result=inspect(s);process.stdout.write(JSON.stringify(result,null,2)+"\n");
    process.exitCode=result.audit_pass?0:2;
  }
}
