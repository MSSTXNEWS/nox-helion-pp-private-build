"""Detect unsafe automatic GitHub Actions jobs that can access NOX OneHost.

Read-only source scanner. It inspects workflow YAML, does not execute Actions,
SSH or provider APIs, and never prints secrets. Native jobs are allowed only
after an explicit owner-triggered workflow_dispatch allow_native=YES gate.

Run: python -m coordination.onepass.native_job_gate_audit [--strict] [--root .]
Requires PyYAML==6.0.2.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml


AUTO_EVENTS=frozenset({"push","pull_request","pull_request_target","schedule",
                       "workflow_run","repository_dispatch","workflow_call"})
NATIVE_PATTERN=re.compile(
    r"""(?i)(secrets\.(?:NOX2|VAST[_A-Z]*|SSH[_A-Z]*|RUNPOD[_A-Z]*KEY)
    |(?:^|[^a-z])NOX2(?:$|[^a-z])
    |ephemeral_ssh_probe
    |vastai\s+(?:execute|ssh|create|destroy|stop|start)
    |supervisorctl\s+(?:restart|stop|start))""",
    re.X|re.M,
)
MANUAL_EVENT=re.compile(
    r"""(?:github\.event_name\s*==\s*['"]workflow_dispatch['"]
      |github\.event\.name\s*==\s*['"]workflow_dispatch['"])""",re.X)
MANUAL_APPROVAL=re.compile(r"""inputs\.(?:allow_native|approve_live|allow_owner_e2e)\s*==\s*['"]YES['"]""")


def _read_yaml(path: Path) -> dict:
    # BaseLoader keeps GitHub's 'on' as a string rather than YAML 1.1 boolean.
    root=yaml.load(path.read_text(encoding="utf8"),Loader=yaml.BaseLoader)
    if not isinstance(root,dict):
        raise ValueError("HOLD_WORKFLOW_YAML_NOT_MAP")
    return root


def _events(doc: dict) -> frozenset[str]:
    raw=doc.get("on",{})
    if isinstance(raw,str):
        return frozenset([raw])
    if isinstance(raw,list):
        return frozenset(str(e) for e in raw)
    if isinstance(raw,dict):
        return frozenset(str(e) for e in raw)
    return frozenset()


def check_workflow(file: Path, *, root: Path) -> tuple[list[dict], list[dict]]:
    doc=_read_yaml(file)
    events=_events(doc)
    jobs=doc.get("jobs",{})
    if not isinstance(jobs,dict):
        raise ValueError("HOLD_WORKFLOW_JOBS_NOT_MAP")
    relative=str(file.relative_to(root)).replace("\\","/")
    unsafe=[]
    native=[]
    for jobid,job in jobs.items():
        if not isinstance(job,dict):
            continue
        # Inspect only executable step definitions and credentials, NOT
        # labels/comments. Step names containing "NOX2" are not network access.
        steps=job.get("steps",[])
        credential_scope={
            "env":job.get("env",{}),
            "uses":[{"run":v.get("run",""),
                     "env":v.get("env",{}),
                     "uses":v.get("uses",""),
                     "with":v.get("with",{})}
                    for v in steps if isinstance(v,dict)] if isinstance(steps,list) else [],
        }
        sensitivity=json.dumps(credential_scope,ensure_ascii=False,sort_keys=True)
        if not NATIVE_PATTERN.search(sensitivity):
            continue
        condition=str(job.get("if",""))
        # A manual-only workflow with a real native job is permitted; to
        # protect future trigger expansion we still recommend input gates.
        no_auto_events=not bool(events&AUTO_EVENTS)
        manual_gated=bool(MANUAL_EVENT.search(condition) and MANUAL_APPROVAL.search(condition))
        protected=manual_gated or no_auto_events
        item={"workflow":relative,"job":str(jobid),"events":sorted(events),
              "manual_gated":manual_gated,"no_automatic_trigger":no_auto_events}
        native.append(item)
        if not protected:
            unsafe.append(item)
    return unsafe,native


def audit(root: Path) -> dict:
    directory=root/".github"/"workflows"
    if not directory.is_dir():
        raise RuntimeError("HOLD_GITHUB_WORKFLOW_DIR_MISSING")
    bad=[]
    native=[]
    parse_failures=[]
    files=sorted([*directory.glob("*.yml"),*directory.glob("*.yaml")])
    if len(files)<5:
        raise RuntimeError("HOLD_WORKFLOW_AUDIT_SCOPE_INCOMPLETE")
    for path in files:
        try:
            u,n=check_workflow(path,root=root)
            bad+=u
            native+=n
        except (ValueError,yaml.YAMLError,UnicodeError) as exc:
            parse_failures.append({
                "workflow":str(path.relative_to(root)),
                "error_type":type(exc).__name__})
    return {"schema":"NOX_V133_ONEHOST_MANUAL_NATIVE_GATES_V1",
            "files_checked":len(files),
            "sensitive_jobs":len(native),
            "unsafe_auto_native_count":len(bad),
            "unsafe_auto_native_jobs":bad,
            "yaml_parse_errors":parse_failures,
            "source_only":True,
            "ssh_connection_attempted":False,
            "owner_secret_exported":False,
            "server_modified":False,
            "release_state":"HOLD" if bad or parse_failures else "SOURCE_POLICY_PASS"}


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",default=".")
    parser.add_argument("--strict",action="store_true")
    parser.add_argument("--out",default="")
    args=parser.parse_args(argv)
    result=audit(Path(args.root).resolve())
    print("NOX_V133_NATIVE_GATES="+json.dumps({
        k:v for k,v in result.items() if k!="unsafe_auto_native_jobs"
    },sort_keys=True,separators=(",",":")))
    for item in result["unsafe_auto_native_jobs"]:
        print("NOX_V133_UNSAFE="+item["workflow"]+"#"+item["job"])
    for item in result["yaml_parse_errors"]:
        print("NOX_V133_YAML_ERROR="+item["workflow"]+":"+item["error_type"])
    if args.out:
        Path(args.out).write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf8")
    if args.strict and (result["unsafe_auto_native_jobs"] or result["yaml_parse_errors"]):
        return 2
    return 0

if __name__=="__main__":
    raise SystemExit(main())
