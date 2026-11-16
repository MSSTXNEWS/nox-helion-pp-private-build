#!/usr/bin/env python3
"""NOX neuro-evolution ingress: only native-verified mentor data.

Produces bounded, provenance-preserving SFT candidates for the EXISTING
trainer. Does NOT execute training, change model weights or touch S03.
"""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile

SCHEMA = "NOX_VERIFIED_EXPERIENCE_V1"
OUT_SCHEMA = "NOX_NEURO_SFT_CANDIDATE_V1"
HEX = re.compile(r"^[0-9a-f]{64}$")
NAME = re.compile(r"^[a-zA-Z0-9_.:-]{1,128}$")
MAX_LINES = 100000
MAX_LINE_BYTES = 32768
TRAINABLE_KINDS = frozenset({
    "bounded_native_component_check", "native_supervisor_running",
    "native_gguf_header", "native_http_health", "native_cgroup_budget",
    "native_adapter_receipt",
})
SOURCE = "owner_dispatcher_native_verification"

def digest(value):
    if not isinstance(value, str):
        value = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return sha256(value.encode()).hexdigest()

def bounded_lines(path):
    if path.is_symlink():
        raise ValueError("HOLD_EXPERIENCE_SYMLINK")
    with path.open("rb") as stream:
        for n, line in enumerate(stream, 1):
            if n > MAX_LINES:
                raise ValueError("HOLD_EXPERIENCE_TOO_MANY_LINES")
            if len(line) > MAX_LINE_BYTES:
                raise ValueError("HOLD_EXPERIENCE_RECORD_SIZE")
            try:
                row = json.loads(line)
            except (ValueError, UnicodeError):
                raise ValueError("HOLD_EXPERIENCE_INVALID_JSON")
            if not isinstance(row, dict):
                raise ValueError("HOLD_EXPERIENCE_RECORD_SHAPE")
            yield row

def checked(row):
    if (row.get("schema") != SCHEMA or row.get("source") != SOURCE
        or row.get("accepted") is not True or row.get("partition") != "train"):
        return None
    group, record_id = row.get("group_sha256"), row.get("dedup_sha256")
    handler, task = row.get("handler"), row.get("task_id")
    proof = row.get("verification")
    if (not isinstance(group,str) or not HEX.fullmatch(group)
        or not isinstance(record_id,str) or not HEX.fullmatch(record_id)
        or not isinstance(handler,str) or not NAME.fullmatch(handler)
        or not isinstance(task,str) or not NAME.fullmatch(task)
        or not isinstance(proof,dict) or proof.get("kind") not in TRAINABLE_KINDS):
        return None
    if (digest({"task":task,"handler":handler}) != group
        or digest({"group":group,"verification":proof}) != record_id):
        return None
    # The original NOX mentor deterministically partitions by GROUP, not
    # by individual sample: never put the same task in train and holdout.
    if int(group[:8],16) % 10 == 0:
        return None
    provenance = row.get("provenance")
    if (not isinstance(provenance,dict)
        or provenance.get("task") != task
        or provenance.get("handler") != handler
        or provenance.get("group_sha256") != group
        or provenance.get("verification") != proof):
        return None
    prompt = "What native evidence verifies the NOX operation " + handler + "?"
    answer = json.dumps(proof,sort_keys=True,ensure_ascii=False)
    if row.get("prompt") != prompt or row.get("answer") != answer:
        return None
    if len(answer.encode("utf-8")) > 10000:
        return None
    # No model-generated recommendations, raw logs or arbitrary prompts.
    return {"schema": OUT_SCHEMA,
            "messages":[
                {"role":"system","content":"Answer only from independently verified NOX native operation evidence; otherwise say unknown."},
                {"role":"user","content":prompt},
                {"role":"assistant","content":answer}],
            "lineage":{"group_sha256":group,"dedup_sha256":record_id,
                       "mentor_source":SOURCE, "task_id":task}}

def build(input_path, holdout_path, output_path):
    holdout = set()
    if holdout_path.is_file():
        for row in bounded_lines(holdout_path):
            group = row.get("group_sha256")
            if (row.get("schema")==SCHEMA and row.get("partition")=="holdout"
                and isinstance(group,str) and HEX.fullmatch(group)):
                holdout.add(group)
    accepted, skipped = {}, 0
    for row in bounded_lines(input_path):
        value = checked(row)
        if not value or value["lineage"]["group_sha256"] in holdout:
            skipped += 1
            continue
        accepted[value["lineage"]["dedup_sha256"]] = value
    if not accepted:
        return {"state":"HOLD_NO_VERIFIED_TRAINING_EVIDENCE","accepted":0,"skipped":skipped,
                "weights_updated":False}
    if output_path.is_symlink():
        raise ValueError("HOLD_OUTPUT_SYMLINK")
    output_path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=".nox-neuro-",dir=output_path.parent)
    try:
        os.fchmod(fd,0o600)
        h=sha256()
        with os.fdopen(fd,"wb") as writer:
            for key in sorted(accepted):
                record=(json.dumps(accepted[key],sort_keys=True,ensure_ascii=False)+"\n").encode()
                writer.write(record)
                h.update(record)
            writer.flush()
            os.fsync(writer.fileno())
        os.replace(tmp,output_path)
        directory=os.open(output_path.parent,os.O_RDONLY | getattr(os,"O_DIRECTORY",0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return {"state":"VERIFIED_CANDIDATE_DATASET_ONLY",
            "accepted":len(accepted),"skipped":skipped,
            "output_sha256":h.hexdigest(),"output":str(output_path),
            "weights_updated":False, "training_started":False}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",default="/root/nox/distill/queue/owner_verified_experience.jsonl")
    parser.add_argument("--holdout",default="/root/nox/distill/queue/owner_experience_holdout.jsonl")
    parser.add_argument("--output",default="/root/nox/distill/queue/owner_neuro_sft_candidates.jsonl")
    args=parser.parse_args()
    report=build(Path(args.source),Path(args.holdout),Path(args.output))
    print("NOX_NEURO_DATASET="+json.dumps(report,ensure_ascii=False,sort_keys=True),flush=True)
    return 0 if report["state"]=="VERIFIED_CANDIDATE_DATASET_ONLY" else 2

if __name__=="__main__":
    raise SystemExit(main())
