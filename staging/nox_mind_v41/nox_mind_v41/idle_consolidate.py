"""Idle consolidation job ("dreaming"/sleep-time compute). Runs only when the system is idle and no STOP/HOLD flag
is present. Default is --dry-run (reports, writes nothing). Not registered in supervisor."""
import argparse, json, os, sys, time
from pathlib import Path
from .graph_memory import GraphMemory

STOP_FLAGS = ["/root/nox/STOP", "/root/nox/STOP.flag", "/root/nox/state/STOP", "/workspace/NOX_STOP"]

def idle(last_activity_ts, idle_minutes, now=None):
    now = time.time() if now is None else now
    return (now - last_activity_ts) >= idle_minutes * 60

def run(db, persona_id, last_activity_ts, idle_minutes=30, dry_run=True, now=None):
    if any(os.path.exists(f) for f in STOP_FLAGS):
        return {"status": "HOLD_STOP_FLAG"}
    if not idle(last_activity_ts, idle_minutes, now):
        return {"status": "SKIP_NOT_IDLE"}
    gm = GraphMemory(db if not dry_run else ":memory:")
    if dry_run:
        src = GraphMemory(db)
        n = src.db.execute("SELECT COUNT(*) FROM node WHERE persona_id=? AND mtype='episodic' AND abstracted=0", (persona_id,)).fetchone()[0]
        return {"status": "DRY_RUN", "pending_episodes": n}
    return {"status": "DONE", **gm.consolidate(persona_id)}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--db", required=True); ap.add_argument("--persona", required=True)
    ap.add_argument("--last-activity", type=float, required=True); ap.add_argument("--idle-minutes", type=int, default=30)
    ap.add_argument("--apply", action="store_true"); a = ap.parse_args()
    print(json.dumps(run(a.db, a.persona, a.last_activity, a.idle_minutes, dry_run=not a.apply), ensure_ascii=False))
