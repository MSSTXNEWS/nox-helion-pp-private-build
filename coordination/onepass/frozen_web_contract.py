"""Reproducible offline audit of ORIGINAL frozen NOX WEB V29.3.

Never extracts or mutates the original ZIP. Distinguishes static callsite
coverage, direct FastAPI route registration, and independent physical E2E.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

ZIP_SHA256 = "166becb90fce63e2db3f9a74281d756995844552cddb7b67a0ac4bd67a190aa0"
ZIP_FILES = 1089
ROUTE_COUNT = 92
NATIVE_EXACT_REGISTRATION = 23
REGISTRATION_RECEIPT = "https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43650605385"
NATIVE_E2E_RECEIPT = "https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43650893956"


def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda:fh.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


def host_boundary(route: str) -> str:
    if route == "/api/pc-metrics" or route.startswith("/api/install/") or (
        route.startswith("/api/voice/") or route == "/api/unified/build"
    ):
        return "WINDOWS_OWNER_PC_OR_LOCAL_RUNTIME_REQUIRES_ACCEPTANCE"
    if route.startswith("/api/ui/services/") or route.startswith("/api/push/") or route.startswith("/api/ui/push/"):
        return "EXTERNAL_PROVIDER_OR_BROWSER_PERMISSION_REQUIRES_CONTRACT"
    return "ONEHOST_OR_CLIENT_BINDING_REQUIRES_CONTRACT"


def find_literal(line: str, route: str) -> bool:
    pattern=re.escape(route)+(r"(?![A-Za-z0-9_./-])" if not route.endswith("/") else "")
    return re.search(pattern,line) is not None


def static_refs(code: str, route: str, name: str) -> list[dict]:
    refs=[]
    for lineno,line in enumerate(code.splitlines(),1):
        if find_literal(line,route):
            refs.append({"file":name,"line":lineno})
            if len(refs)>=12:
                break
    return refs


def analyze(zip_path: Path, matrix_path: Path) -> dict:
    if sha256_file(zip_path)!=ZIP_SHA256:
        raise ValueError("HOLD_FROZEN_ZIP_SHA256_CHANGED")
    with zipfile.ZipFile(zip_path) as frozen:
        info=frozen.infolist()
        if len(info)!=ZIP_FILES or frozen.testzip() is not None:
            raise ValueError("HOLD_FROZEN_ZIP_CRC_OR_FILE_COUNT")
        if any(Path(file.filename).is_absolute() or ".." in Path(file.filename).parts for file in info):
            raise ValueError("HOLD_FROZEN_ZIP_PATH_UNSAFE")
        matrix=json.loads(matrix_path.read_text(encoding="utf-8"))
        routes=[f["route"] for f in matrix["functions"]]
        if len(routes)!=ROUTE_COUNT or len(set(routes))!=ROUTE_COUNT:
            raise ValueError("HOLD_FROZEN_ROUTE_MATRIX_92")
        source={}
        for filename in sorted(frozen.namelist()):
            if not filename.startswith("site/") or not filename.endswith((".js",".mjs",".html")):
                continue
            raw=frozen.read(filename)
            if len(raw)>3_000_000:
                raise ValueError("HOLD_FROZEN_SOURCE_SIZE")
            source[filename[5:]]=raw.decode("utf8",errors="replace")
    result=[]
    for route in sorted(routes):
        evidence=[]
        for filename,code in source.items():
            evidence.extend(static_refs(code,route,filename))
        result.append({
            "route":route,
            "static_references":evidence[:24],
            "static_source_found":bool(evidence),
            "host_scope":host_boundary(route),
            "exact_native_registration": "UNKNOWN_UNVERIFIED_IN_THIS_OFFLINE_RUN",
            "functional_e2e": "UNKNOWN_UNVERIFIED_IN_THIS_OFFLINE_RUN",
            "method_or_payload_verified":False,
        })
    return {
        "schema":"NOX_ONEPASS_FROZEN_WEB_V29_3_STATIC_CONTRACT_V1",
        "zip_sha256":ZIP_SHA256,
        "zip_entries":ZIP_FILES,
        "static_sources_inspected":len(source),
        "expected_api_routes":len(result),
        "historical_direct_route_count":NATIVE_EXACT_REGISTRATION,
        "historical_direct_route_evidence":REGISTRATION_RECEIPT,
        "previous_stream_s03_evidence":NATIVE_E2E_RECEIPT,
        "unknown_or_unmapped_native_count_historical":ROUTE_COUNT-NATIVE_EXACT_REGISTRATION,
        "historical_direct_registered_means_e2e_pass":False,
        "independent_windows_owner_acceptance_pass":False,
        "full_weight_optimizer_checkpoint_restore_pass":False,
        "functions":result,
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--zip",required=True,type=Path)
    parser.add_argument("--matrix",type=Path,default=Path("coordination/NOX_V98_WEB_FULL_REAL_API_MATRIX.json"))
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    result=analyze(args.zip,args.matrix)
    summary={k:v for k,v in result.items() if k!="functions"}
    print("NOX_ONEPASS_FROZEN_SOURCE="+json.dumps(summary,ensure_ascii=False,sort_keys=True))
    if args.output is not None:
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf8")


if __name__=="__main__":
    main()
