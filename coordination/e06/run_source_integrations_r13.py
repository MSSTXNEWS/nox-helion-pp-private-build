"""NOX V16 R13: deterministic ONEHOST source integration test runner.

Source FIRST (V16 §46). Never builds EXE/NSIS, starts external LLM, installs
models, or changes canonical source. Local owner fixtures are byte-identical
temporary copies, not new service implementations or native acceptance.
Run from repository checkout: python coordination/e06/run_source_integrations_r13.py
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
P02=ROOT/"Packages"/"P02"/"worker-python"
P03=ROOT/"Packages"/"P03"/"Source"/"python-host"
PACK=ROOT/"proposals"/"NOX-PACK01-50"
E06_TESTS=ROOT/"tests"/"e06"
ADAPTER_TESTS=E06_TESTS/"adapters"
CREATIVE_TESTS=ROOT/"integrations"/"creative"/"tests"

SUITES=(
    ("PACK01 immutable UTF8/consent",E06_TESTS,"test_pack01_native_utf8_boundary_r03.py"),
    ("PACK01 owner batch rollback",E06_TESTS,"test_pack01_owner_batch_r10.py"),
    ("Immutable P02/P03/E06 contracts",E06_TESTS,"test_immutable_routes_p03_e06_r11.py"),
    ("G2 source binder and rollback",E06_TESTS,"test_immutable_onehost_binder_r12.py"),
    ("WOW owner/runtime registry",E06_TESTS,"test_wow_owner_runtime_preflight_r06.py"),
    ("WOW exact 200 catalog IDs and compositions",E06_TESTS,"test_wow200_catalog_integrity_r02.py"),
    ("Creative verified worker STOP R19",E06_TESTS,"test_creative_stop_exit_attestation_r19.py"),
    ("Creative local weight SHA receipts R20",CREATIVE_TESTS,"test_weight_receipts_r20.py"),
    ("Creative R31 bundled regressions",CREATIVE_TESTS,"test_*_r31.py"),
    ("P02 native frames",P02,"test_p02_native_ingress.py"),
    ("P03 ModelCenter real owner adapter",P03,"test_p03_onehost_port.py"),
    ("G2 source integration owner fixtures",ADAPTER_TESTS,"test_g2_space_mobile.py"),
)

def files_for(source:Path):
    if not source.is_dir() or source.is_symlink():
        raise RuntimeError("SOURCE_ROOT_MISSING_OR_REPARSE:"+str(source))
    result=[]
    for base,folders,files in os.walk(source,followlinks=False):
        for name in folders+files:
            part=Path(base)/name
            if part.is_symlink():
                raise RuntimeError("OWNER_SOURCE_REPARSE_HOLD:"+str(part))
        for name in files:
            part=Path(base)/name
            if part.is_file() and "__pycache__" not in part.parts:
                result.append(part)
    return sorted(result)

def snapshot_owner(source:Path,destination:Path)->int:
    original=files_for(source)
    if sum(p.stat().st_size for p in original)>100_000_000:
        raise RuntimeError("OWNER_SOURCE_COPY_OVER_BUDGET")
    shutil.copytree(source,destination,ignore=shutil.ignore_patterns("__pycache__","*.pyc"))
    # Verify actual bytes, not only filenames or mtimes.
    for file in original:
        relative=file.relative_to(source)
        peer=destination/relative
        if not peer.is_file():
            raise RuntimeError("OWNER_FIXTURE_FILE_MISSING:"+str(relative))
        a=hashlib.sha256(file.read_bytes()).digest()
        b=hashlib.sha256(peer.read_bytes()).digest()
        if a!=b:
            raise RuntimeError("OWNER_FIXTURE_SHA_MISMATCH:"+str(relative))
    return len(original)

def main()->int:
    required=[P02/"p02_native_ingress.py",P03/"p03_onehost_port.py",
              PACK/"native_bridge.py",PACK/"catalog.json",
              ADAPTER_TESTS/"test_g2_space_mobile.py"]
    if any(not p.is_file() or p.is_symlink() for p in required):
        print("HOLD: CANONICAL_OWNER_SOURCES_MISSING_OR_REPARSE",flush=True)
        return 2

    with tempfile.TemporaryDirectory(prefix="nox-v16-r13-source-") as temp:
        fixtures=Path(temp)/"owners"
        fixtures.mkdir()
        copied={
            "P02":snapshot_owner(P02,fixtures/"P02"),
            "P03":snapshot_owner(P03,fixtures/"P03"),
            "PACK01":snapshot_owner(PACK,fixtures/"PACK01"),
        }
        env=os.environ.copy()
        env.update({
            "PYTHONDONTWRITEBYTECODE":"1",
            "NOX_PINNED_P02_PATH":str(P02),
            "NOX_PINNED_PACK01_PATH":str(PACK),
            "NOX_G2_OWNER_FIXTURE_ROOT":str(fixtures),
        })
        print("R13 SOURCE FIXTURE SHA VERIFIED",copied,flush=True)
        failed=[]
        for label,folder,pattern in SUITES:
            if not (folder/pattern).is_file():
                print("HOLD: SOURCE_TEST_MISSING",label,pattern,flush=True)
                failed.append(label)
                continue
            cmd=[sys.executable,"-m","unittest","discover",
                 "-s",str(folder),"-p",pattern,"-v"]
            print("R13 START",label,flush=True)
            check=subprocess.run(cmd,cwd=ROOT,env=env,check=False)
            print("R13 RESULT",label,"PASS" if check.returncode==0 else "HOLD",
                  flush=True)
            if check.returncode!=0:
                failed.append(label)
        if failed:
            print("R13 SOURCE_READY=HOLD; FAILED",failed,flush=True)
            return 1
    print("R13 COMPONENT_SUITES_PASS; WINDOWS_E07_NOT_RUN; SOURCE_READY_REQUIRES_FULL_OWNER_QA",
          flush=True)
    return 0

if __name__=="__main__":
    sys.exit(main())
