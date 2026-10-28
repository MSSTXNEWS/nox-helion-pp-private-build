#!/usr/bin/env python3
"""Astra ten-agent/ten-pass evidence-only dashboard. SOURCE ONLY, NO BUILD.
python coordination/astra/render_astra_progress_r24.py --matrix coordination/astra/ASTRA_V16_R23_10_AGENTS_X_10_APPROACHES.json
A matrix with only planned work prints 0/10 and PRODUCT=N/D, not fake 100%.
"""
from __future__ import annotations
import argparse
import json
import pathlib
import re
import sys

SHA=re.compile(r"^[0-9a-f]{40}$")

def actual_done(p: dict)->bool:
    """Only verified source passes with immutable Git SHA + actual test PASS count."""
    if p.get("status")!="COMPLETED":
        return False
    if not isinstance(p.get("evidence_git_sha"),str) or not SHA.fullmatch(p["evidence_git_sha"]):
        return False
    tests=p.get("tests")
    return (isinstance(tests,list) and len(tests)>0
            and all(isinstance(t,dict) and t.get("status")=="PASS"
                    and isinstance(t.get("command"),str) and t["command"].strip()
                    and isinstance(t.get("output_receipt"),str) and t["output_receipt"].strip()
                    for t in tests))

def report(matrix:dict)->str:
    agents=matrix["agents"]
    if len(agents)!=10 or len({a["id"] for a in agents})!=10:
        raise ValueError("EXPECTED_EXACTLY_TEN_AGENT_ROLES")
    rendered=["NOX ASTRA SOURCE R24 | EVIDENCE-BASED PROGRESS (NOT RELEASE ACCEPTANCE)"]
    total=0
    for agent in agents:
        if len(agent.get("approaches",[]))!=10:
            raise ValueError("TEN_SOURCE_APPROACHES_REQUIRED:"+agent["id"])
        completed=sum(actual_done(x) for x in agent["approaches"])
        total+=completed
        bar="["+"#"*completed+"."*(10-completed)+"]"
        spawned=("SPAWN_RECEIPT_PRESENT" if agent.get("actual_spawn_receipt")
                 else "SPAWN_NOT_VERIFIED")
        rendered.append(f'{agent["id"]} {bar} {completed}/10 PASSES | {spawned} | {agent["role"]}')
    rendered.append(f'REAL SOURCE APPROACHES: {total}/100 (ONLY EVIDENCE-VERIFIED)')
    for block,weight in (("P01",20),("P02",25),("P03",20),("P04",25),("P05",10)):
        score=matrix.get("product_verified_task_progress",{}).get(block)
        if (not isinstance(score,dict) or
            not isinstance(score.get("denominator"),int) or score["denominator"]<=0 or
            not isinstance(score.get("verified_done"),int) or
            not 0<=score["verified_done"]<=score["denominator"]):
            rendered.append(f"{block} (weight {weight}%): PRODUCT Н/Д — fixed TaskID coverage not verified")
        else:
            n=score["verified_done"]; d=score["denominator"]
            rendered.append(f"{block} (weight {weight}%): {100*n/d:.1f}% ({n}/{d} TaskIDs; evidence check required)")
    rendered.append("SOURCELOCK raw ZIP+729: HOLD unless separately verified; INTEGRATION: NOT_STARTED; Windows EXE: NOT_BUILT; E07: 0/10 NOT_RUN")
    rendered.append("DRIVE: require run-report + active-error-master + self-improvement CAS append and RunID readback each launch")
    return "\n".join(rendered)

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("--matrix",default="coordination/astra/ASTRA_V16_R23_10_AGENTS_X_10_APPROACHES.json")
    a=p.parse_args()
    try:
        matrix=json.loads(pathlib.Path(a.matrix).read_text(encoding="utf-8"))
        print(report(matrix))
        return 0
    except (OSError,ValueError,KeyError,TypeError) as e:
        print("ASTRA_PROGRESS_HOLD: "+str(e)[:240],file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
