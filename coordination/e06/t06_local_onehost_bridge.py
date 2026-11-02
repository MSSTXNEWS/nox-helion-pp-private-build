"""T06 ONEHOST LOCAL BRIDGE · one Windows VM, two proven component builds.
No external HTTP artifact fetch, zero new host/server, no SourceLock rewrite.
The only completed status is a diagnostic installer candidate, NOT an E07 pass.
"""
from __future__ import annotations
import hashlib,json,os,pathlib,subprocess,sys,time

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
        # E07 preflight at zero extra runner startups: original owner NSIS
        # silent install, exact same binary SHA, framed IPC, conservative remove.
        # A missing WebView2 runtime marks an explicit hold, never fake PASS.
        third=run("03_INSTALLED_NSIS_NATIVE_SMOKE",
                  ROOT/"coordination/e06/t06_samevm_installed_smoke.py",env,530)
        steps.append(third)
        smokePath=OUT/"T06_INSTALLED_SMOKE.json"
        if not smokePath.is_file():
            raise RuntimeError("T06_SAME_VM_SMOKE_RECEIPT_MISSING")
        smoke=json.loads(smokePath.read_text("utf-8"))
        data["installed_smoke_phase"]=smoke.get("phase","HOLD")
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
            item_count=0
            for item in summary.get("files",[]):
                name=item.get("name")
                if not isinstance(name,str) or "/" in name or "\\" in name or \
                   name in ("",".",".."):
                    raise RuntimeError("NOX_MEGA814_RESOURCE_NAME_INVALID")
                f=packaged/name
                if not f.is_file() or f.is_symlink() or \
                   f.stat().st_size!=item.get("bytes") or \
                   digest(f)!=item.get("sha256"):
                    raise RuntimeError("NOX_MEGA814_PAYLOAD_SHA_DRIFT:"+name)
                item_count+=1
            if item_count!=14:
                raise RuntimeError("NOX_MEGA814_MENU14_COUNT_HOLD")
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
        data["phase"]="ONEHOST_NSIS_CANDIDATE_SOURCE_ONLY"
        data["setup_sha256"]=onehost["setup_sha256"]
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
