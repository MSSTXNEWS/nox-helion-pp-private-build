"""Onepass GitHub Actions native admission fix, source-only.

Only edits YAML in a checkout. No OneHost, S03, weights or secrets are accessed.
Commit is permitted by CI only after strict full-tree YAML/manual gate checks.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path
import yaml
from coordination.onepass.native_job_gate_audit import audit

GATE=("github.event_name == 'workflow_dispatch' && "
      "inputs.allow_native == 'YES' && github.actor == 'MSSTXNEWS'")
INPUTS=[
    "    inputs:",
    "      allow_native:",
    "        description: 'Owner-approved original NOX OneHost access only'",
    "        type: choice",
    "        required: true",
    "        options: ['NO', 'YES']",
    "        default: 'NO'",
]
JOB_HEADING=re.compile(r'^  ([A-Za-z][A-Za-z0-9_-]*):\s*$')
JOB_IF=re.compile(r'^    if:\s*')
ON_MANUAL=re.compile(r'^  workflow_dispatch:\s*(.*)$')
PUSH_ONLY=re.compile(r"""github\.event_name\s*==\s*(['"])(?:push|pull_request|pull_request_target)\1""")


def _yaml(content:str)->dict:
    doc=yaml.load(content,Loader=yaml.BaseLoader)
    if not isinstance(doc,dict):
        raise RuntimeError("HOLD_WORKFLOW_YAML")
    return doc


def transform(raw:str,jobs:list[str],*,path:str)->str:
    if not jobs:return raw
    original=_yaml(raw)
    oldjobs=original.get("jobs",{})
    if not isinstance(oldjobs,dict):
        raise RuntimeError("HOLD_NONMAP_JOBS:"+path)
    lines=raw.splitlines(keepends=False)
    on=next((i for i,s in enumerate(lines) if s=="on:"),-1)
    root=next((i for i,s in enumerate(lines) if s=="jobs:"),-1)
    if on<0 or root<0 or on>=root:
        raise RuntimeError("HOLD_UNSUPPORTED_WORKFLOW:"+path)
    for jobid in jobs:
        if jobid not in oldjobs or not isinstance(oldjobs[jobid],dict):
            raise RuntimeError("HOLD_UNEXPECTED_JOB:"+path+":"+jobid)
        found=[i for i in range(root+1,len(lines))
               if lines[i]=="  "+jobid+":"]
        if len(found)!=1:
            raise RuntimeError("HOLD_UNSUPPORTED_JOB_HEADING:"+path+":"+jobid)
        first=found[0]
        end=next((i for i in range(first+1,len(lines))
                  if JOB_HEADING.fullmatch(lines[i])),len(lines))
        conditions=[i for i in range(first+1,end) if JOB_IF.match(lines[i])]
        if len(conditions)>1:
            raise RuntimeError("HOLD_MULTIPLE_JOB_IF:"+path+":"+jobid)
        old_if=oldjobs[jobid].get("if")
        if old_if is not None and not isinstance(old_if,str):
            raise RuntimeError("HOLD_INVALID_IF:"+path+":"+jobid)
        if bool(conditions)!=(old_if is not None):
            raise RuntimeError("HOLD_INCONSISTENT_JOB_IF:"+path+":"+jobid)
        existing=old_if.strip() if old_if else ""
        if existing.startswith("$"+"{{") and existing.endswith("}}"):
            existing=existing[3:-2].strip()
        existing=" ".join(x.strip() for x in existing.splitlines())
        existing=PUSH_ONLY.sub("github.event_name == 'workflow_dispatch'",existing)
        if existing and ("inputs.allow_native == 'YES'" in existing
                         and "github.event_name == 'workflow_dispatch'" in existing):
            condition=existing
        else:
            condition=GATE + (" && ("+existing+")" if existing else "")
        expression="$"+"{{ "+condition+" }}"
        replacement="    if: "+json.dumps(expression,ensure_ascii=False)
        if not conditions:
            lines.insert(first+1,replacement)
        else:
            i=conditions[0]
            j=i+1
            while j<len(lines):
                if (JOB_HEADING.fullmatch(lines[j])
                    or re.match(r'^    [A-Za-z][A-Za-z0-9_-]*:',lines[j])):
                    break
                if lines[j] and not lines[j].startswith("      "):
                    break
                j+=1
            lines[i:j]=[replacement]
    on=lines.index("on:")
    root=lines.index("jobs:")
    manual=[i for i in range(on+1,root) if ON_MANUAL.match(lines[i])]
    if len(manual)>1:
        raise RuntimeError("HOLD_MULTIPLE_MANUAL_EVENTS:"+path)
    if not manual:
        lines[on+1:on+1]=["  workflow_dispatch:",*INPUTS]
    else:
        i=manual[0]
        check=ON_MANUAL.match(lines[i])
        if check is None or check.group(1).strip() not in ("","{}"):
            raise RuntimeError("HOLD_INLINE_MANUAL:"+path)
        lines[i]="  workflow_dispatch:"
        after=next((j for j in range(i+1,len(lines))
                    if lines[j] and not lines[j].startswith(" ")),len(lines))
        ids=[j for j in range(i+1,after) if lines[j]=="    inputs:"]
        if len(ids)>1:
            raise RuntimeError("HOLD_MULTIPLE_INPUTS:"+path)
        if ids:
            j=ids[0]
            limit=next((k for k in range(j+1,after)
                        if re.match(r'^    [A-Za-z][A-Za-z0-9_-]*:',lines[k])),after)
            fragment=lines[j+1:limit]
            if not any(x=="      allow_native:" for x in fragment):
                lines[j+1:j+1]=INPUTS[1:]
            elif not any("default: 'NO'" in x or 'default: "NO"' in x for x in fragment):
                raise RuntimeError("HOLD_NATIVE_INPUT_NOT_DEFAULT_NO:"+path)
        else:
            lines[i+1:i+1]=INPUTS
    out="\n".join(lines)+("\n" if raw.endswith("\n") else "")
    validated=_yaml(out)
    if set(validated.get("jobs",{}))!=set(oldjobs):
        raise RuntimeError("HOLD_LOST_OR_ADDED_SOURCE_JOB:"+path)
    for jobid in jobs:
        expression=validated["jobs"][jobid].get("if","")
        if not (isinstance(expression,str)
                and "inputs.allow_native == 'YES'" in expression
                and "github.event_name == 'workflow_dispatch'" in expression):
            raise RuntimeError("HOLD_MANUAL_GATE_NOT_PRESENT:"+path+":"+jobid)
    return out


def run(root:Path,*,apply:bool=False)->dict:
    original=audit(root)
    if original["yaml_parse_errors"]:
        raise RuntimeError("HOLD_PREEXISTING_WORKFLOW_YAML")
    targets={}
    for item in original["unsafe_auto_native_jobs"]:
        targets.setdefault(item["workflow"],set()).add(item["job"])
    changes={}
    for name,ids in sorted(targets.items()):
        location=(root/name).resolve()
        if not location.is_relative_to(root) or location.suffix not in (".yml",".yaml"):
            raise RuntimeError("HOLD_UNSAFE_WORKFLOW_PATH")
        old=location.read_text(encoding="utf8")
        new=transform(old,sorted(ids),path=name)
        if old==new:
            raise RuntimeError("HOLD_UNCHANGED_UNSAFE_NATIVE_JOB:"+name)
        changes[name]=new
    if apply:
        for name,new in changes.items():
            (root/name).write_text(new,encoding="utf8")
        check=audit(root)
        if check["unsafe_auto_native_count"] or check["yaml_parse_errors"]:
            raise RuntimeError("HOLD_NATIVE_POLICY_POST_APPLY")
    evidence={k:hashlib.sha256(v.encode()).hexdigest() for k,v in changes.items()}
    return {"schema":"NOX_V133_ONEPASS_NATIVE_WORKFLOW_SAFETY",
            "files_scanned":original["files_checked"],
            "unsafe_jobs_before":original["unsafe_auto_native_count"],
            "changed_files":len(changes),
            "source_diff_sha256":hashlib.sha256(
                json.dumps(evidence,sort_keys=True).encode()).hexdigest(),
            "unsafe_jobs_remaining":0 if apply else None,
            "applied":apply,"original_model_or_s03_touched":False,
            "provider_accessed":False,"git_source_only":True}


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--root",default=".")
    p.add_argument("--apply",action="store_true")
    p.add_argument("--out",default="")
    args=p.parse_args(argv)
    receipt=run(Path(args.root).resolve(),apply=args.apply)
    print("NOX_V133_ONEPASS_GUARD="+json.dumps(receipt,sort_keys=True,separators=(",",":")))
    if args.out:
        Path(args.out).write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf8")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
