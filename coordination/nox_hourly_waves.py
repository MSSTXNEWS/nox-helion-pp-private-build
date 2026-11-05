#!/usr/bin/env python3
"""NOX V16 three hourly waves × five non-destructive engineering gates.

Every wave continues EXACT owner commit IDs and the original source commit
from its predecessor's immutable GitHub Actions artifact. No source merge,
auto-edit, network exposure, installed weights, GPU training or fake EXE QA.
"""
from __future__ import annotations
import argparse, ast, datetime as dt, hashlib, io, json, os, pathlib
import re, subprocess, sys, urllib.error, urllib.request, zipfile

WORKFLOW = "nox-hourly-three-groups.yml"
WAVE_BY_CRON = {"20 * * * *":"A", "40 * * * *":"B", "0 * * * *":"C"}
PREVIOUS = {"A":"C", "B":"A", "C":"B"}
OWNER_PRS = {"1":28,"2":13,"3":17,"4":12,"5":9}
OWNER_FILES = {
 "1":["stage/proposals/P01/C09/Installer/Build-NSIS.ps1",
      "stage/proposals/P01/C09/Installer/Verify-Payload.ps1"],
 "2":["Packages/P02/worker-python/p02_runtime.py",
      "Packages/P02/worker-python/p02_capabilities.py"],
 "3":["Packages/P03/C40/INTEGRATION_RECEIPT.md",
      "Packages/P03/C40/NOX_V16_E03_C40_P03_CLOSURE_CANDIDATE.zip"],
 "4":["Packages/P04/train_qlora.py",
      "Packages/P04/Rag/RagService.cs"],
 "5":["Packages/P05/E05/src/E05Telemetry.cs",
      "Packages/P05/E05/src/E05SafeFeedClient.cs"]
}
FOLLOWUP_FILES = {
 "1":["stage/proposals/P01/C09/Installer/Preflight-InstallPath.ps1",
      "stage/proposals/P01/C09/Installer/Remove-InstalledPayload.ps1"],
 "2":["Packages/P02/worker-python/p02_host_probe.py"],
 "3":["Packages/P03/C40/NOX_V16_E03_TURBO10_from_C40.patch"],
 "4":["Packages/P04/Rag/RagChatContextProvider.cs",
      "Packages/P04/GpuGuardian/GpuGuardian.cs"],
 "5":["Packages/P05/E05/src/E05Progress.cs",
      "Packages/P05/E05/src/E05SpaceParsing.cs"]
}
SHA = re.compile(r"^[0-9a-f]{40}$")
MAX_STALE = dt.timedelta(hours=2)

def json_bytes(obj):
    return json.dumps(obj,ensure_ascii=False,sort_keys=True,
        separators=(",",":")).encode("utf-8")

def sha256(data):
    return hashlib.sha256(data).hexdigest()

def utcnow():
    return dt.datetime.now(dt.timezone.utc)

def parsed_iso(value):
    return dt.datetime.fromisoformat(value.replace("Z","+00:00"))

def api(repo, route, token, *, binary=False):
    url = "https://api.github.com/repos/"+repo+"/"+route
    req=urllib.request.Request(url,headers={
        "Accept":"application/vnd.github+json",
        "Authorization":"Bearer "+token,
        "X-GitHub-Api-Version":"2022-11-28",
        "User-Agent":"nox-v16-hourly-waves"})
    with urllib.request.urlopen(req,timeout=25) as response:
        raw=response.read(6_000_001)
    if len(raw)>6_000_000:
        raise RuntimeError("GITHUB_RESPONSE_OVERSIZE")
    return raw if binary else json.loads(raw.decode("utf-8"))

def choose_wave(args):
    if args.event=="workflow_dispatch":
        if args.requested not in ("A","B","C"):raise ValueError("UNKNOWN_DISPATCH_WAVE")
        return args.requested
    if args.event!="schedule" or args.cron not in WAVE_BY_CRON:
        raise ValueError("UNRECOGNIZED_SCHEDULE_OR_EVENT")
    return WAVE_BY_CRON[args.cron]

def find_predecessor(repo,token,previous,source_sha,now):
    data=api(repo,"actions/workflows/"+WORKFLOW+"/runs?status=completed&per_page=65",token)
    for run in data.get("workflow_runs",[]):
        if run.get("conclusion")!="success" or run.get("event") not in ("schedule","workflow_dispatch"):
            continue
        ended=run.get("updated_at")
        if not ended or not dt.timedelta(0)<=now-parsed_iso(ended)<=MAX_STALE:
            continue
        run_id=run.get("id")
        artifacts=api(repo,"actions/runs/"+str(run_id)+"/artifacts?per_page=40",token)
        candidates=[x for x in artifacts.get("artifacts",[]) if
            x.get("name")=="nox-wave-"+previous+"-state" and not x.get("expired")]
        if not candidates:continue
        zipped=api(repo,"actions/artifacts/"+str(candidates[0]["id"])+"/zip",token,binary=True)
        with zipfile.ZipFile(io.BytesIO(zipped)) as arc:
            if arc.namelist()!=["state.json"]:raise RuntimeError("PREVIOUS_ARTIFACT_LAYOUT_DRIFT")
            state=json.loads(arc.read("state.json"))
        verify_state(state,previous)
        if state["source_sha"]!=source_sha:
            raise RuntimeError("HOLD_SOURCE_VERSION_CHANGED_REQUIRES_RECONCILIATION")
        return state
    return None

def verify_state(s,expected_wave):
    if not isinstance(s,dict) or s.get("schema")!="NOX-HOURLY-WAVES-V1":
        raise RuntimeError("STATE_SCHEMA_INVALID")
    if s.get("wave")!=expected_wave or not SHA.fullmatch(s.get("source_sha","")):
        raise RuntimeError("STATE_VERSION_INVALID")
    owners=s.get("owner_sha",{})
    if set(owners)!=set(OWNER_PRS) or any(not SHA.fullmatch(v) for v in owners.values()):
        raise RuntimeError("OWNER_SHA_DRIFT")
    receipts=s.get("receipts")
    if not isinstance(receipts,list) or len(receipts)!=5 or {r.get("slot") for r in receipts}!={1,2,3,4,5}:
        raise RuntimeError("FIVE_RECEIPTS_REQUIRED")
    if any(r.get("status")!="PASS" or r.get("source_sha")!=s["source_sha"] or
           r.get("owner_sha")!=owners[str(r.get("slot"))] for r in receipts):
        raise RuntimeError("PREDECESSOR_GATES_FAILED")
    if not isinstance(s.get("chain_index"),int) or s["chain_index"]<1:
        raise RuntimeError("CHAIN_ID_INVALID")

def prepare(args):
    wave=choose_wave(args)
    if not SHA.fullmatch(args.source_sha):raise RuntimeError("INVALID_BASE_HEAD")
    now=utcnow()
    prev=find_predecessor(args.repo,args.token,PREVIOUS[wave],args.source_sha,now)
    if prev is None and wave!="A":
        raise RuntimeError("HOLD_PREDECESSOR_NOT_COMPLETE_"+PREVIOUS[wave])
    if prev:
        if prev["wave"]!=PREVIOUS[wave]:raise RuntimeError("WRONG_WAVE_ORDER")
        owner_sha=prev["owner_sha"].copy()
        chain_id=prev["chain_id"]
        chain_index=prev["chain_index"]+1
        previous_run=prev["run_id"]
    else:
        # Only A may start a new chain; B and C must truly continue its receipt.
        owner_sha={}
        for owner,num in OWNER_PRS.items():
            pr=api(args.repo,"pulls/"+str(num),args.token)
            value=pr.get("head",{}).get("sha","")
            if not SHA.fullmatch(value):raise RuntimeError("OWNER_PR_HEAD_UNVERIFIED_"+owner)
            owner_sha[owner]=value
        chain_id="nox-"+str(args.run_id)
        chain_index=1
        previous_run=None
    state={"schema":"NOX-HOURLY-INPUT-V1","wave":wave,"source_sha":args.source_sha,
           "owner_sha":owner_sha,"chain_id":chain_id,"chain_index":chain_index,
           "previous_run_id":previous_run,"run_id":int(args.run_id),
           "phase":{"A":"SOURCE_PRESERVATION","B":"COMPONENT_CONTRACT",
                    "C":"MERGE_READINESS"}[wave]}
    pathlib.Path(args.out).write_text(json.dumps(state,indent=2)+"\n",encoding="utf-8")
    with open(os.environ["GITHUB_OUTPUT"],"a",encoding="utf-8") as out:
        out.write("wave="+wave+"\n")
        out.write("source_sha="+args.source_sha+"\n")
        out.write("chain_id="+chain_id+"\n")
    print("NOX_WAVE",wave,"PHASE",state["phase"],"OWNER_COUNT",len(owner_sha),
          "CHAIN",chain_id,"PREVIOUS_RUN",previous_run)

def git(*arguments, text=True):
    x=subprocess.run(["git",*arguments],check=True,capture_output=True)
    return x.stdout.decode("utf-8").strip() if text else x.stdout

def check(args):
    data=json.loads(pathlib.Path(args.input).read_text(encoding="utf-8"))
    if data.get("schema")!="NOX-HOURLY-INPUT-V1" or not SHA.fullmatch(data.get("source_sha","")):
        raise RuntimeError("INVALID_PREPARED_INPUT")
    if git("rev-parse","HEAD")!=data["source_sha"]:
        raise RuntimeError("HOLD_CHECKOUT_CHANGED")
    slot=str(args.slot)
    owner_sha=data["owner_sha"][slot]
    num=OWNER_PRS[slot]
    git("fetch","--no-tags","--depth=1","origin","refs/pull/"+str(num)+"/head")
    if git("rev-parse","FETCH_HEAD")!=owner_sha:
        raise RuntimeError("HOLD_OWNER_VERSION_CHANGED")
    files=OWNER_FILES[slot]+(FOLLOWUP_FILES[slot] if data["wave"]=="C" else [])
    checks=[]
    for path in files:
        raw=git("show","FETCH_HEAD:"+path,text=False)
        if not raw or len(raw)>3_000_000:raise RuntimeError("OWNER_FILE_INVALID_"+path)
        if data["wave"] in ("B","C") and path.endswith(".py"):
            ast.parse(raw.decode("utf-8"),filename=path)
        if data["wave"]=="C" and path.endswith(".cs"):
            if b"namespace " not in raw or b"class " not in raw:
                raise RuntimeError("CS_SOURCE_STRUCTURE_MISSING_"+path)
        if data["wave"]=="C" and path.endswith(".ps1"):
            if not any(b in raw.lower() for b in (b"throw",b"exit",b"erroractionpreference")):
                raise RuntimeError("PS_SAFE_FAIL_GATE_MISSING_"+path)
        checks.append({"path":path,"sha256":sha256(raw),"bytes":len(raw)})
    if data["wave"]=="C":
        required={
          "1":("Build-NSIS.ps1","Verify-Payload.ps1"),
          "2":("p02_runtime.py","p02_host_probe.py"),
          "3":("INTEGRATION_RECEIPT.md","TURBO10_from_C40.patch"),
          "4":("train_qlora.py","GpuGuardian.cs"),
          "5":("E05Telemetry.cs","E05Progress.cs")
        }
        for term in required[slot]:
            if not any(term in c["path"] for c in checks):
                raise RuntimeError("ORIGINAL_OWNER_FUNCTION_MISSING_"+term)
    receipt={"slot":args.slot,"status":"PASS","phase":data["phase"],
             "source_sha":data["source_sha"],"owner_sha":owner_sha,
             "pr":num,"chain_id":data["chain_id"],"checks":checks,
             "note":"Source evidence only; not installed EXE, trained GPU or five AI agents"}
    pathlib.Path(args.out).write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    print("NOX_SLOT_PASS",args.slot,"WAVE",data["wave"],"OWNER_SHA",owner_sha,
          "SOURCES",len(checks))

def publish(args):
    source=json.loads(pathlib.Path(args.input).read_text(encoding="utf-8"))
    receipts=[]
    for slot in range(1,6):
        p=pathlib.Path(args.root)/("nox-slot-"+str(slot))/"receipt.json"
        if not p.is_file():raise RuntimeError("HOLD_MISSING_SLOT_RECEIPT_"+str(slot))
        item=json.loads(p.read_text(encoding="utf-8"))
        if (item.get("slot")!=slot or item.get("status")!="PASS" or
            item.get("source_sha")!=source["source_sha"] or
            item.get("owner_sha")!=source["owner_sha"][str(slot)] or
            item.get("chain_id")!=source["chain_id"] or
            item.get("phase")!=source["phase"]):
            raise RuntimeError("HOLD_SLOT_EVIDENCE_MISMATCH_"+str(slot))
        receipts.append(item)
    state={"schema":"NOX-HOURLY-WAVES-V1","wave":source["wave"],
           "source_sha":source["source_sha"],"owner_sha":source["owner_sha"],
           "chain_id":source["chain_id"],"chain_index":source["chain_index"],
           "previous_run_id":source["previous_run_id"],"run_id":source["run_id"],
           "receipts":receipts,"published_at_utc":utcnow().isoformat(),
           "release_accepted":False,"original_source_changed":False}
    verify_state(state,state["wave"])
    pathlib.Path(args.out).write_text(json.dumps(state,indent=2)+"\n",encoding="utf-8")
    print("NOX_WAVE_COMPLETE",state["wave"],"SLOTS",len(receipts),
          "CHAIN_INDEX",state["chain_index"],"RELEASE_ACCEPTED",False)

def selftest():
    assert [WAVE_BY_CRON[x] for x in ("20 * * * *","40 * * * *","0 * * * *")]==["A","B","C"]
    assert [PREVIOUS[x] for x in ("A","B","C")]==["C","A","B"]
    assert set(OWNER_FILES)==set(OWNER_PRS)=={"1","2","3","4","5"}
    assert all(len(v)==2 for v in OWNER_FILES.values())
    try:verify_state({}, "A")
    except RuntimeError:pass
    else:raise AssertionError("Missing state must fail closed")
    print("NOX_THREE_WAVE_SELFTEST_PASS five owner routes, three hourly phases, strict state gate")

def main():
    ap=argparse.ArgumentParser()
    sub=ap.add_subparsers(dest="action",required=True)
    for name in ("prepare","check","publish"):
        p=sub.add_parser(name)
        if name=="prepare":
            for opt in ("repo","token","source-sha","run-id","event","cron","requested","out"):
                p.add_argument("--"+opt,required=True)
        if name=="check":
            p.add_argument("--slot",type=int,choices=range(1,6),required=True)
            p.add_argument("--input",required=True);p.add_argument("--out",required=True)
        if name=="publish":
            p.add_argument("--input",required=True);p.add_argument("--root",required=True)
            p.add_argument("--out",required=True)
    sub.add_parser("selftest")
    args=ap.parse_args()
    if args.action=="prepare":prepare(args)
    elif args.action=="check":check(args)
    elif args.action=="publish":publish(args)
    else:selftest()

if __name__=="__main__":
    main()
