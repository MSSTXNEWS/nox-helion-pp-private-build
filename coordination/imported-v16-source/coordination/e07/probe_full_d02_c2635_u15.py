"""Real independent Windows UIA click QA on the existing full D02 Setup, never a release."""
from __future__ import annotations
import argparse,json,os,struct,sys
from pathlib import Path
import independent_setup_e07 as e07
from probe_five_primary_action import evaluate

SOURCE="30cbd21782eacd452363d6c65899fd5e57a24d1c"
SETUP_SHA="c2635c56b4d742973df50ff07f1647d1c0c4ff4689b8a94b02b79b7fbf0d8b99"
BYTES=169607673
BUILDID="NOX-V16-4808dde05af9293a073db03f"
def candidate(folder):
    root=folder/"e06"/"onehost-wow-diagnostic"
    setup=root/"NOX-HELION-V16-DIAGNOSTIC-SETUP.exe"
    e07.require(e07.clean_dir(folder) and e07.clean_dir(root) and e07.clean_file(setup),
                "D02_ARTIFACT_PATH_HOLD")
    h=e07._read_locked_e06_json(root/"E07_BUILT_HANDOFF.json")
    d=e07._read_locked_e06_json(root/"ONEHOST_DIAGNOSTIC_RECEIPT.json")
    s=e07._read_locked_e06_json(root/"T06_INSTALLED_SMOKE.json")
    e07.require(
        h.get("schema")=="NOX_V16_E07_IMMUTABLE_HANDOFF_V1"
        and h.get("source_commit_sha1")==SOURCE and h.get("setup_sha256")==SETUP_SHA
        and h.get("build_id")==BUILDID and h.get("source_files")==729
        and h.get("source_receipts_729_parity_verified") is True
        and h.get("independent_e07_cases_accepted")==0
        and h.get("release_accepted") is False
        and d.get("schema")=="NOX-E06-ONEHOST-DIAGNOSTIC-NSIS-v1"
        and d.get("source_commit_sha1")==SOURCE and d.get("installer_sha256")==SETUP_SHA
        and d.get("installer_bytes")==BYTES and d.get("release_accepted") is False
        and s.get("schema")=="NOX-T06-INSTALLED-SMOKE-v1"
        and s.get("setup_sha256")==SETUP_SHA and s.get("build_id")==BUILDID
        and s.get("manifest_files_checked")==1004 and s.get("release_accepted") is False
        and s.get("e07_independent_acceptance")=="NOT_RUN"
        and e07.samevm_lifecycle_verified(s.get("installer_lifecycle"),expected_owned_files=1004),
        "D02_EXACT_PRODUCER_RECEIPT_HOLD")
    e07.require(setup.stat().st_size==BYTES,"D02_SETUP_SIZE_HOLD")
    digest,header=e07.installed_file_sha_locked(
        setup,root.resolve(strict=True),BYTES,SETUP_SHA,return_pe_header=True)
    e07.require(digest==SETUP_SHA and len(header)>=64 and header[:2]==b"MZ",
                "D02_SETUP_PE_SHA_HOLD")
    offset=struct.unpack_from("<I",header,0x3c)[0]
    e07.require(offset<=len(header)-6 and header[offset:offset+4]==b"PE\0\0",
                "D02_SETUP_PE_SHA_HOLD")
    return setup
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--artifact-dir",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    result={"source_sha":SOURCE,"setup_sha256":SETUP_SHA,"build_id":BUILDID,
            "schema":"NOX-E07-FULL-D02-UIA-v1","checks":{},
            "five_uia":"HOLD","independent_e07_10_10":"HOLD",
            "release_accepted":False,"error":"NOT_RUN"}
    try:
        e07.require(sys.platform=="win32" and os.environ.get("GITHUB_ACTIONS")=="true"
                    and os.environ.get("RUNNER_OS")=="Windows"
                    and os.environ.get("RUNNER_ENVIRONMENT")=="github-hosted"
                    and os.environ.get("GITHUB_REPOSITORY")=="MSSTXNEWS/nox-helion-pp-private-build",
                    "D02_INDEPENDENT_WINDOWS_ONLY_HOLD")
        setup=candidate(a.artifact_dir)
        result["physical_setup_verified"]=True
        e07.lifecycle(setup,result,physical_nav=True)
        result["five_primary"]=evaluate(result["checks"]["installed_gui"])
        result["five_uia"]="PASS"
        result["error"]=None
    except (e07.Hold,OSError,ValueError,KeyError,TimeoutError) as exc:
        result["error"]=(str(exc) if isinstance(exc,e07.Hold)
                         else "D02_"+type(exc).__name__.upper()+"_HOLD")[:160]
    finally:
        a.out.parent.mkdir(parents=True,exist_ok=True)
        a.out.write_text(json.dumps(result,sort_keys=True,indent=2),encoding="utf-8")
        print("NOX_D02_FIVE_REAL_UIA",result["five_uia"],result["error"],flush=True)
    return 0 if result["five_uia"]=="PASS" else 1
if __name__=="__main__":
    raise SystemExit(main())
