"""NOX V16 R13: deterministic ONEHOST source integration test runner.

Source FIRST (V16 §46). Never builds EXE/NSIS, starts external LLM, installs
models, or changes canonical source. Local owner fixtures are byte-identical
temporary copies, not new service implementations or native acceptance.
Run from repository checkout: python coordination/e06/run_source_integrations_r13.py
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from t06_closeout_guard import decide as decide_t06_closeout

ROOT=Path(__file__).resolve().parents[2]
P02=ROOT/"Packages"/"P02"/"worker-python"
P03=ROOT/"Packages"/"P03"/"Source"/"python-host"
PACK=ROOT/"proposals"/"NOX-PACK01-50"
E06_TESTS=ROOT/"tests"/"e06"
A1_TESTS=ROOT/"tests"/"a1"
ADAPTER_TESTS=E06_TESTS/"adapters"
HOST50_TESTS=ROOT/"coordination"/"e06_host50"
G2_ADAPTERS=ROOT/"coordination"/"e06"/"adapters"
P01_INSTALLER=ROOT/"stage"/"proposals"/"P01"/"C09"/"Installer"
CREATIVE_TESTS=ROOT/"integrations"/"creative"/"tests"

SUITES=(
    ("PACK01 immutable UTF8/consent",E06_TESTS,"test_pack01_native_utf8_boundary_r03.py"),
    ("PACK01 owner batch rollback",E06_TESTS,"test_pack01_owner_batch_r10.py"),
    ("P01 restic BSD-2-Clause native backup/restore source-only 13 cases",PACK,"test_p01_restic_backup_port.py"),
    ("Immutable P02/P03/E06 contracts",E06_TESTS,"test_immutable_routes_p03_e06_r11.py"),
    ("G2 source binder and rollback",E06_TESTS,"test_immutable_onehost_binder_r12.py"),
    ("T06 one-host P02 duplicate-route native ACL regression",E06_TESTS,"test_t06_r09_native_source_owner.py"),
    ("T06 existing E06 mobile source binding (native still HOLD)",HOST50_TESTS,"test_t06_mobile_binding_r26.py"),
    ("P01 NSIS-PowerShell source CLI contract; no compiler",E06_TESTS,"test_t06_p01_nsis_powershell_contract_r15.py"),
    ("P01 PS5.1 JSON reader rejects duplicate manifest properties (source-only)",E06_TESTS,"test_p01_manifest_duplicate_reader_r35.py"),
    ("P01 original WPF donor full namespace preflight",E06_TESTS,"test_stage_p01_shared_zip_guard.py"),
    ("WOW owner/runtime registry",E06_TESTS,"test_wow_owner_runtime_preflight_r06.py"),
    ("WOW exact 200 catalog IDs and compositions",E06_TESTS,"test_wow200_catalog_integrity_r02.py"),
    ("Creative verified worker STOP R19",E06_TESTS,"test_creative_stop_exit_attestation_r19.py"),
    ("Creative local weight SHA receipts R20",CREATIVE_TESTS,"test_weight_receipts_r20.py"),
    ("Creative R31 bundled regressions",CREATIVE_TESTS,"test_*_r31.py"),
    ("P02 native frames",P02,"test_p02_native_ingress.py"),
    ("P02 OwnerTwoPorts live PACK01 ACL and native rollback",P02,"test_p02_owner_route_ports.py"),
    ("P03 ModelCenter real owner adapter",P03,"test_p03_onehost_port.py"),
    ("G2 source integration owner fixtures",ADAPTER_TESTS,"test_g2_space_mobile.py"),
    ("FASTLANE2 existing task selection and immutable handoff ERR25",E06_TESTS,"test_fastlane2_accelerator.py"),
    ("A1 WPF native owner MAC/SID/run/nonce proof (source only)",A1_TESTS,"test_a1_wpf_owner_proof.py"),
    ("A1 optional FirstBoot vs read-only signed research consent",A1_TESTS,"test_a1_independent_consent.py"),

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
            if part.is_file() and "__pycache__" not in part.parts and part.suffix != ".pyc":
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

def main(*, closeout_receipt: Path | None = None)->int:
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
            "HOST50":snapshot_owner(HOST50_TESTS,fixtures/"HOST50"),
            "G2_ADAPTERS":snapshot_owner(G2_ADAPTERS,fixtures/"G2"),
            "P01_INSTALLER":snapshot_owner(P01_INSTALLER,fixtures/"P01Installer"),
        }
        env=os.environ.copy()
        env.update({
            "PYTHONDONTWRITEBYTECODE":"1",
            "NOX_PINNED_P02_PATH":str(fixtures/"P02"),
            "NOX_PINNED_PACK01_PATH":str(fixtures/"PACK01"),
            "NOX_PINNED_G2_PATH":str(fixtures/"G2"),
            "NOX_PINNED_P01_INSTALLER_PATH":str(fixtures/"P01Installer"),
            "NOX_G2_OWNER_FIXTURE_ROOT":str(fixtures),
        })
        print("R13 SOURCE FIXTURE SHA VERIFIED",copied,flush=True)
        failed=[]
        for label,folder,pattern in SUITES:
            # Owner tests must import the SHA-verified copies, not mutable live paths.
            source_folder = (fixtures/"P02" if folder == P02 else
                             fixtures/"P03" if folder == P03 else
                             fixtures/"HOST50" if folder == HOST50_TESTS else folder)
            matches=list(source_folder.glob(pattern)) if "*" in pattern else [source_folder/pattern]
            if not matches or any(not match.is_file() or match.is_symlink() for match in matches):
                print("HOLD: SOURCE_TEST_MISSING",label,pattern,flush=True)
                failed.append(label)
                continue
            cmd=[sys.executable,"-m","unittest","discover",
                 "-s",str(source_folder),"-p",pattern,"-v"]
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
    if closeout_receipt is None:
        # Component tests do not imply source-owner or independent acceptance.
        return 0
    if closeout_receipt.is_symlink() or not closeout_receipt.is_file():
        print("HOLD: T06_CLOSEOUT_RECEIPT_MISSING_OR_REPARSE", flush=True)
        return 2
    if closeout_receipt.stat().st_size > 1_000_000:
        print("HOLD: T06_CLOSEOUT_RECEIPT_UNBOUNDED", flush=True)
        return 2
    try:
        closeout = decide_t06_closeout(json.loads(closeout_receipt.read_text(encoding="utf-8")))
    except (OSError, ValueError, UnicodeError, TypeError) as exc:
        print("HOLD: T06_CLOSEOUT_RECEIPT_INVALID", type(exc).__name__, flush=True)
        return 2
    print("T06_SOURCE_OWNER_CLOSEOUT", json.dumps(closeout, ensure_ascii=False), flush=True)
    return 0 if closeout["done"] else 2

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--closeout-receipt", type=Path,
                        help="8-criterion owner source acceptance receipt; never implies T10 SOURCE_READY")
    options=parser.parse_args()
    sys.exit(main(closeout_receipt=options.closeout_receipt))
