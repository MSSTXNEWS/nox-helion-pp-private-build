"""T06 ONEHOST LOCAL BRIDGE · one Windows VM, two proven component builds.
No external HTTP artifact fetch, zero new host/server, no SourceLock rewrite.
The only completed status is a diagnostic installer candidate, NOT an E07 pass.
"""
from __future__ import annotations
import hashlib,json,os,pathlib,subprocess,sys,time,re,stat
from t06_compile_original_wpf_p02 import verified_source_head
from t06_package_original_onehost import EXPECTED_ZIP_SHA
from t06_source_receipt_guard import attest_candidate

ROOT=pathlib.Path(__file__).resolve().parents[2]
OUT=ROOT/"work/t06-local-bridge"
PRODUCER=ROOT/"coordination/e06/t06_native_proven_builder.py"
CONSUMER=ROOT/"coordination/e06/t06_compile_original_wpf_p02.py"
RESULT=ROOT/"work/t06-wpf-p02-compile/ONEHOST_CANDIDATE_RECEIPT.json"
PYRECEIPT=ROOT/"work/t06-manual-source-inspect/python-exe-candidate/NATIVE_PYTHON_EXE_CANDIDATE_RECEIPT.json"
def digest(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        while chunk:=f.read(1024*1024):h.update(chunk)
    return h.hexdigest()
def run(label,script,env,timeout):
    start=time.monotonic()
    log=OUT/(label+".log")
    with log.open("wb") as out:
        try:
            p=subprocess.run([sys.executable,str(script)],cwd=ROOT,
                env=env,stdout=out,stderr=subprocess.STDOUT,
                timeout=timeout,check=False)
            code=p.returncode
        except subprocess.TimeoutExpired:
            code=124
    return {"step":label,"return_code":code,"elapsed_seconds":round(time.monotonic()-start,2),"log":log.name}
def webview2_root_evidence(lifecycle):
    """Bounded allowlisted SAME-VM runtime evidence, never an install or E07 grant.

    Previous Windows job logged signed downloads but hid the actual two install
    exit codes and explicit registry views inside a >300 MB artifact. This
    summary contains only non-secret version/error/status fields.
    """
    if type(lifecycle) is not dict:
        return {"status":"LIFECYCLE_ABSENT_NOT_E07"}
    versions=("HKLM_32_VIEW","HKLM_64_VIEW","HKCU_32_VIEW",
              "HKCU_64_VIEW","HKCU_USER")
    stages={"initial":"webview2_initial_registration",
            "bootstrapper":"webview2_evergreen-bootstrapper_registration_diagnostic",
            "standalone":"webview2_evergreen-standalone-x64_registration_diagnostic"}
    statuses={"PASS","RUNTIME_MISSING","UNRELATED_HOLD"}
    verdicts={"PASS_BY_ORIGINAL_PREFLIGHT","RUNTIME_MISSING",
              "UNRELATED_HOLD","REGISTRY_PREFLIGHT_DIVERGENCE"}
    sources={"evergreen-bootstrapper","evergreen-standalone-x64"}
    source=lifecycle.get("webview2_selected_verified_source")
    proof={"selected_source":source if type(source) is str and source in sources else "UNKNOWN",
           "installer":{},"registration":{},"poll":{},"verdict":{},
           "final_preflight_exit":None,"release_accepted":False}
    for name,key in (("initial","microsoft_webview2_provision_ci"),
                     ("standalone","webview2_standalone_fallback")):
        entry=lifecycle.get(key)
        if type(entry) is dict:
            code=entry.get("exit_code")
            kind=entry.get("kind")
            proof["installer"][name]={
                "exit_code":code if type(code) is int and -10000<=code<=10000 else None,
                "kind":kind if type(kind) is str and kind in sources else "UNKNOWN",
                "signed_microsoft":entry.get("signed_microsoft") is True}
    for name,key in stages.items():
        registry=lifecycle.get(key)
        if type(registry) is not dict:
            continue
        safe={}
        for view in versions:
            row=registry.get(view)
            if type(row) is not dict:
                continue
            version=row.get("pv")
            winerror=row.get("winerror")
            safe[view]={
                "present":row.get("present") is True,
                "pv":version if type(version) is str and
                     re.fullmatch(r"[0-9]+(?:\.[0-9]+){3}",version) else None,
                "winerror":winerror if type(winerror) is int and
                           -100000<=winerror<=100000 else None}
        proof["registration"][name]=safe
    for name,label in (("bootstrapper","evergreen-bootstrapper"),
                       ("standalone","evergreen-standalone-x64")):
        entries=lifecycle.get("webview2_"+label+"_strict_preflight_poll")
        safe=[]
        if type(entries) is list:
            for row in entries[:8]:
                if type(row) is not dict:
                    continue
                state=row.get("strict_preflight_status")
                code=row.get("exit_code")
                delay=row.get("delay_seconds")
                safe.append({"status":state if type(state) is str and
                             state in statuses else "UNKNOWN",
                             "exit_code":code if type(code) is int and -10000<=code<=10000 else None,
                             "delay_seconds":delay if type(delay) is int and 0<=delay<=120 else None})
        proof["poll"][name]=safe
        verdict=lifecycle.get("webview2_"+label+"_strict_preflight_verdict")
        proof["verdict"][name]=(verdict if type(verdict) is str and
                                 verdict in verdicts else "UNKNOWN")
    final=lifecycle.get("webview2_final_postinstall_preflight")
    if type(final) is dict and type(final.get("code")) is int:
        proof["final_preflight_exit"]=final["code"]
    return proof


def _no_reparse_components(path):
    """Reject redirected ancestors before admitting original NSIS payload bytes.

    Both the packaged directory and each asset must have a trusted full path:
    a direct child can have correct SHA even when an ancestor junction points
    to another tree. Windows junction/reparse and POSIX symlinks fail closed.
    This is source admission, not an E07/TOCTOU-proof installed-file claim.
    """
    for node in (path, *path.parents):
        try:
            info = node.lstat()
        except OSError:
            return False
        if (stat.S_ISLNK(info.st_mode) or
                bool(getattr(info, "st_file_attributes", 0) &
                     getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)) or
                getattr(node, "is_junction", lambda: False)()):
            return False
    return True


def verify_mega814_payload_files(packaged, summary):
    """Verify fourteen DISTINCT original NSIS assets, not fourteen manifest rows.

    The receipt is source-only: never infer a rendered GUI or independent E07.
    Reject Windows case-folded duplicates, reparse redirects and path aliases.
    """
    entries = summary.get("files") if type(summary) is dict else None
    if type(entries) is not list or len(entries) != 14:
        raise RuntimeError("NOX_MEGA814_MENU14_COUNT_HOLD")
    if (not packaged.is_dir() or not _no_reparse_components(packaged)):
        raise RuntimeError("NOX_MEGA814_PACKAGE_PATH_UNTRUSTED")
    seen = set()
    for item in entries:
        if type(item) is not dict:
            raise RuntimeError("NOX_MEGA814_RESOURCE_ENTRY_INVALID")
        name = item.get("name")
        if (type(name) is not str or name in ("", ".", "..") or
                name.strip() != name or "/" in name or "\\" in name or
                ":" in name or "\x00" in name or name.casefold() in seen):
            raise RuntimeError("NOX_MEGA814_RESOURCE_NAME_INVALID_OR_DUPLICATE")
        file = packaged / name
        expected_size = item.get("bytes")
        expected_sha = item.get("sha256")
        if (not file.is_file() or not _no_reparse_components(file) or
                type(expected_size) is not int or expected_size < 0 or
                type(expected_sha) is not str or
                re.fullmatch(r"[0-9a-f]{64}", expected_sha) is None or
                file.stat().st_size != expected_size or
                digest(file) != expected_sha):
            raise RuntimeError("NOX_MEGA814_PAYLOAD_SHA_DRIFT:" + name)
        seen.add(name.casefold())
    return len(seen)

def main():
    if OUT.exists() or OUT.is_symlink():
        raise SystemExit("T06_LOCAL_BRIDGE_OUTPUT_COLLISION")
    OUT.mkdir(parents=True)
    steps=[];t0=time.monotonic()
    data={"schema":"NOX-T06-SAME-VM-ONEHOST-v1",
          "gitlab_ref":os.getenv("CI_COMMIT_REF_NAME","manual"),
          "gitlab_sha":os.getenv("CI_COMMIT_SHA","UNVERIFIED"),
          "steps":steps,"phase":"HOLD","release_accepted":False,
          "original_archives_modified":False,
          "wpf_interactive_qa":"NOT_RUN","independent_e07":"NOT_RUN"}
    try:
        source_head=verified_source_head()
        env=dict(os.environ);env["PYTHONUNBUFFERED"]="1"
        # Stage and SHA-verify the immutable 729-file original Python once.
        first=run("01_NATIVE_PYINSTALLER",PRODUCER,env,900)
        steps.append(first)
        if first["return_code"]!=0 or not PYRECEIPT.is_file():
            raise RuntimeError("T06_LOCAL_NATIVE_PRODUCER_FAILED")
        py=json.loads(PYRECEIPT.read_text("utf-8"))
        executable=PYRECEIPT.with_name("NOX_HELION_PRIVATE_CANDIDATE.exe")
        if py.get("phase")!="BUILT_AND_NATIVE_STDIO_SMOKE_PASS" or \
           py.get("native_windows_exe_request_reply")!="PASS" or \
           not executable.is_file() or executable.is_symlink() or \
           digest(executable)!=py.get("exe_sha256"):
            raise RuntimeError("T06_LOCAL_NATIVE_PYTHON_SHA_OR_IPC_HOLD")
        # Stage and compile original R11 once, then package directly from same
        # private Windows filesystem: zero JobID URLs, token or artifact 404.
        env["NOX_T06_PACKAGE_CANDIDATE"]="YES"
        second=run("02_WPF_NSIS_ONEHOST",CONSUMER,env,1100)
        steps.append(second)
        if second["return_code"]!=0 or not RESULT.is_file():
            raise RuntimeError("T06_LOCAL_WPF_NSIS_CONSUMER_FAILED")
        onehost=json.loads(RESULT.read_text("utf-8"))
        if onehost.get("backend_sha256")!=py["exe_sha256"] or \
           onehost.get("backend_native_stdio_windows_exe_smoke")!="PASS" or \
           onehost.get("wpf_source_compilation")!="PASS" or \
           onehost.get("release_accepted") is not False:
            raise RuntimeError("T06_LOCAL_SAME_BINARY_SHA_OR_SOURCE_HOLD")
        # Bind current checkout, original 729 files, WPF compile and real NSIS
        # bytes BEFORE any installed smoke, never borrow a historical receipt.
        setup_path=ROOT/"work/t06-wpf-p02-compile/NOX-HELION-V16-ONEHOST-CANDIDATE-SETUP.exe"
        frozen_setup_sha=attest_candidate(
            source_head,ROOT/"work/t06-wpf-p02-compile/T06_COMPILE_EVIDENCE.json",
            RESULT,setup_path,EXPECTED_ZIP_SHA)
        # E07 preflight at zero extra runner startups: original owner NSIS
        # silent install, exact same binary SHA, framed IPC, conservative remove.
        # A missing WebView2 runtime marks an explicit hold, never fake PASS.
        # The original same-VM verifier reads this LOCAL R11/NSIS receipt set,
        # never the unrelated older e06/onehost-wow diagnostic build.
        env["NOX_T06_LOCAL_BRIDGE"]="YES"
        third=run("03_INSTALLED_NSIS_NATIVE_SMOKE",
                  ROOT/"coordination/e06/t06_samevm_installed_smoke.py",env,530)
        steps.append(third)
        smokePath=OUT/"T06_INSTALLED_SMOKE.json"
        if not smokePath.is_file():
            raise RuntimeError("T06_SAME_VM_SMOKE_RECEIPT_MISSING")
        smoke=json.loads(smokePath.read_text("utf-8"))
        data["installed_smoke_phase"]=smoke.get("phase","HOLD")
        # One physical four-gate run: print the *real* failed installed step
        # before any generic HOLD. Keep source hashes and release gates unchanged.
        lifecycle=smoke.get("installer_lifecycle",{})
        # Persist all *safe* error evidence even if the following G4 gate fails.
        # A 302MB GitLab artifact cannot be a prerequisite for root diagnosis.
        runtime_evidence=webview2_root_evidence(lifecycle)
        data["webview2_root_evidence"]=runtime_evidence
        print("T06_WEBVIEW2_RUNTIME_ROOT_EVIDENCE "+
              json.dumps(runtime_evidence,ensure_ascii=False,sort_keys=True,
                         separators=(",",":")),flush=True)
        report={
            "reason":smoke.get("reason",""),
            "phase":smoke.get("phase","HOLD"),
            "webview2":lifecycle.get("webview2_signature_attempts",[]),
            "webview2_preflight":lifecycle.get("preflight_final",{}),
            "nsis_install":lifecycle.get("install",{}),
            "native_ipc":lifecycle.get("native_ipc",{}),
            "wpf_gui":lifecycle.get("original_wpf_gui",{}),
            "home_media_sha_ok":smoke.get("original_home_and_core01_sha_verified",False),
        }
        print("NOX_EXPRESS_GATE_4_INSTALLED_RESULT "+json.dumps(report,ensure_ascii=False,sort_keys=True)[:8000],flush=True)
        if (third["return_code"]!=0 or
            smoke.get("phase")!="INSTALLED_GUI_IPC_UPDATE_ROLLBACK_NOLOSS_PASS_NOT_E07" or
            smoke.get("installer_lifecycle",{}).get("original_wpf_gui",{}).get("new_nav_ok") is not True or
            smoke.get("installer_lifecycle",{}).get("original_wpf_gui",{}).get("new_python_ipc_handshake") is not True or
            smoke.get("original_home_and_core01_sha_verified") is not True):
            raise RuntimeError("T06_M1_REAL_WINDOWS_GUI_IPC_LIFECYCLE_GATE_HOLD")
        # The same SHA-locked R11 Assets MUST be present in the final NSIS
        # payload. A passing C# compiler alone is not a visual integration.
        if env.get("NOX_MEGA_8_14")=="YES":
            attested=onehost.get("mega814")
            if (not isinstance(attested,dict) or
                attested.get("status")!="VERIFIED_IN_SAME_NSIS_PAYLOAD_NOT_E07" or
                attested.get("asset_count")!=14 or
                attested.get("menu10_sha256")!="1cdc1d9d6f17033bf4a1c6a8ec1b8f5816ab35ddd5ed6d682eb8a190e1943dca" or
                attested.get("release_accepted") is not False):
                raise RuntimeError("T06_MEGAB_R76_ONEHOST_RECEIPT_NOT_PINNED")
            staged=ROOT/"work/t06-wpf-p02-compile/R11/Assets/mega814"
            packaged=ROOT/"work/t06-wpf-p02-compile/payload/Assets/mega814"
            proof=staged/"MEGA814_RECEIPT.json"
            if not proof.is_file() or not packaged.is_dir():
                raise RuntimeError("NOX_MEGA814_NOT_PRESENT_IN_NSIS_PAYLOAD")
            summary=json.loads(proof.read_text("utf-8"))
            if summary.get("status")!="SOURCE_MOUNTED_NOT_E07" or \
               summary.get("worlds")!=10 or summary.get("work_views")!=8 or \
               summary.get("legacy_routes")!=54 or summary.get("visual_criteria")!=30 or \
               summary.get("release_accepted") is not False:
                raise RuntimeError("NOX_MEGA814_SOURCE_RECEIPT_NOT_ACCEPTABLE")
            item_count=verify_mega814_payload_files(packaged,summary)
            source_index=ROOT/"work/t06-wpf-p02-compile/R11/Assets/index.html"
            packaged_index=ROOT/"work/t06-wpf-p02-compile/payload/Assets/index.html"
            if not source_index.is_file() or not packaged_index.is_file() or \
               digest(source_index)!=digest(packaged_index) or \
               digest(source_index)!=summary.get("staged_sha256"):
                raise RuntimeError("NOX_MEGA814_INDEX_SOURCE_TO_SETUP_DRIFT")
            data["mega814"]={
              "status":"BUNDLED_IN_NSIS_SOURCE_ONLY",
              "menu_worlds":10,"work_views":8,"legacy_route_ids":54,
              "personas":5,"visual_criteria_accepted":0,
              "source_file_count":item_count,
              "image10_sha_verified":summary.get("menu10_asset_verified") is True,
              "personas_sha_verified":summary.get("personas_asset_verified"),
              "index_sha256":summary["staged_sha256"],
              "e07_gui_visual":"HOLD"
            }
            print("NOX_MEGA814_SETUP_PAYLOAD_PINNED",item_count,"files",flush=True)
        if (verified_source_head()!=source_head or not setup_path.is_file() or
            setup_path.is_symlink() or digest(setup_path)!=frozen_setup_sha):
            raise RuntimeError("T06_SOURCE_OR_SETUP_CHANGED_AFTER_NATIVE_SMOKE")
        data["phase"]="ONEHOST_NSIS_CANDIDATE_SOURCE_ONLY"
        data["source_git_sha"]=source_head
        data["setup_sha256"]=frozen_setup_sha
        data["backend_sha256"]=py["exe_sha256"]
        print("T06_LOCAL_BRIDGE_ONEHOST_NSIS_CANDIDATE_PASS",
              data["setup_sha256"],flush=True)
    except Exception as e:
        data["error"]=str(e)[:230]
        print("T06_LOCAL_BRIDGE_HOLD",data["error"],flush=True)
    finally:
        data["elapsed_seconds"]=round(time.monotonic()-t0,2)
        (OUT/"ONEHOST_LOCAL_BRIDGE_RESULT.json").write_text(
            json.dumps(data,ensure_ascii=False,indent=2),"utf-8")
    return 0 if data["phase"]=="ONEHOST_NSIS_CANDIDATE_SOURCE_ONLY" else 1

if __name__=="__main__":
    raise SystemExit(main())
