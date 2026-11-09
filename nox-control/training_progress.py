#!/usr/bin/env python3
"""NOX training progress inspector: read-only, no imports from NOX, no process changes."""
import argparse
import datetime as dt
import json
import re
import subprocess
import time
from pathlib import Path

EXCLUDED = {"site-packages", ".git", "node_modules", "models", "weights", "tokenizers", "datasets", "cache", "venv", "prime9b-venv"}
TEXT_SUFFIXES = {".log", ".json", ".jsonl", ".txt"}
STEP_PATTERNS = [
    re.compile(r'(?i)\b(?:global_step|optimizer_step|train_step|training_step|step)\s*["\':= ]+\s*(\d{1,9})\s*(?:/|of)\s*(\d{1,9})'),
    re.compile(r'(?i)\b(?:global_step|optimizer_step|train_step|training_step|step)\s*["\':= ]+\s*(\d{1,9})')
]
TOTAL_PATTERNS = [
    re.compile(r'(?i)\b(?:max_steps|total_steps|planned_steps|target_steps|num_training_steps)\s*["\':= ]+\s*(\d{1,9})')
]
LOSS_PATTERN = re.compile(r'(?i)\b(?:train_loss|training_loss|loss)\s*["\':= ]+\s*(-?\d+(?:\.\d+)?(?:e[-+]?\d+)?)')
ERROR_PATTERN = re.compile(r'(?i)(CUDA out of memory|OutOfMemoryError|Traceback \(most recent call last\)|RuntimeError:|training failed)')
STEP_KEYS = ("global_step", "optimizer_step", "train_step", "training_step", "step")
TOTAL_KEYS = ("max_steps", "total_steps", "planned_steps", "target_steps", "num_training_steps")

def integer(value):
    try:
        if isinstance(value, bool): return None
        val = int(value)
        return val if 0 <= val <= 1000000000 else None
    except (TypeError, ValueError, OverflowError): return None

def latest_text_files(root):
    found = []
    if not root.is_dir(): return found
    for p in root.rglob("*"):
        if any(k in EXCLUDED or k.endswith("-venv") for k in p.parts): continue
        if not p.is_file() or p.suffix.lower() not in TEXT_SUFFIXES: continue
        try:
            s = p.stat()
        except OSError: continue
        if s.st_size > 25_000_000 or s.st_size == 0: continue
        name = str(p).lower()
        if not any(word in name for word in ("train", "distill", "progress", "checkpoint", "/logs/", "supervisor")): continue
        found.append((s.st_mtime, p))
    return [p for _, p in sorted(found, reverse=True)[:70]]

def read_tail(p, n=2_000_000):
    with p.open("rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size-n))
        raw = f.read()
    return raw.decode("utf-8", "replace")

def extract_lines(text):
    steps, total, losses, errors = [], [], [], []
    for line in text.splitlines():
        if len(line)>6000: continue
        step = None
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                for key in STEP_KEYS:
                    if key in obj:
                        step = integer(obj[key]); break
                for key in TOTAL_KEYS:
                    if key in obj: 
                        n=integer(obj[key])
                        if n: total.append(n)
                for key in ("train_loss", "loss"):
                    if isinstance(obj.get(key), (float,int)): losses.append(float(obj[key]));break
        except (ValueError, TypeError): pass
        for pat in STEP_PATTERNS:
            m = pat.search(line)
            if m:
                step = integer(m.group(1))
                if m.lastindex and m.lastindex>=2:
                    n=integer(m.group(2))
                    if n: total.append(n)
                break
        if step is not None: steps.append(step)
        for pat in TOTAL_PATTERNS:
            m=pat.search(line)
            if m:
                n=integer(m.group(1))
                if n: total.append(n)
        m=LOSS_PATTERN.search(line)
        if m:
            try: losses.append(float(m.group(1)))
            except ValueError: pass
        if ERROR_PATTERN.search(line): errors.append(line[:180])
    return steps, total, losses, errors

def inspect(root, goal):
    files = latest_text_files(root)
    candidates = []
    errors=[]
    for p in files:
        try:
            steps, totals, losses, errs = extract_lines(read_tail(p))
            errors.extend([{"file":str(p.relative_to(root)), "message":msg} for msg in errs[-2:]])
            if steps:
                mtime=p.stat().st_mtime
                # A single file may span resets or multiple runs; do not merge files/runs.
                last=steps[-1]
                # Estimated rate is deliberately withheld unless timestamped step samples exist.
                candidates.append((mtime, str(p.relative_to(root)), last, totals[-1] if totals else None, losses[-1] if losses else None))
        except (OSError, UnicodeError): continue
    candidates.sort(reverse=True)
    current=candidates[0] if candidates else None
    step=current[2] if current else None
    total=goal or (current[3] if current else None)
    pct=round(step/total*100,2) if step is not None and total and step<=total else None
    remaining=max(0,total-step) if step is not None and total else None
    ckpts=[]
    if root.exists():
        for folder in (root/"checkpoints",root/"checkpoint",root/"outputs",root/"distillation",root/"training"):
            if folder.is_dir():
                try:
                    for p in folder.iterdir():
                        if p.is_dir() and ("checkpoint" in p.name.lower() or p.name.startswith("step-")):
                            ckpts.append({"name":p.name,"path":str(p)})
                except OSError: pass
    ckpts=ckpts[-15:]
    return {
        "protocol":"NOX_TRAINING_PROGRESS_V1", "checked_at":dt.datetime.now(dt.timezone.utc).isoformat(),
        "root":str(root), "observed_files":len(files),
        "last_step":step, "total_steps":total, "remaining_steps":remaining, "percent_of_planned_steps":pct,
        "step_source":current[1] if current else None, "last_loss":current[4] if current else None,
        "eta_seconds":None, "eta_reason":"Timestamped successive optimizer steps not verified",
        "checkpoint_directories":ckpts,
        "errors_seen_in_recent_log_files":errors[-6:],
        "training_verified":False,
        "training_verification_reason":"Log step counters alone do not prove that model weights or adapters changed; checkpoint and training process must be verified separately",
        "distillation_skill_transfer_percent":None,
        "note":"Progress of a plan is not proof of successful distillation. This inspector never stops processes or modifies files."
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",default="/workspace/nox")
    p.add_argument("--total-steps",type=int,default=0,help="Only use an independently verified target")
    args=p.parse_args()
    print(json.dumps(inspect(Path(args.root),args.total_steps or None),ensure_ascii=False,indent=2))

if __name__=="__main__": main()
