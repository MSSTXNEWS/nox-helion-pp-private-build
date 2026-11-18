#!/usr/bin/env python3
"""t162u dynamic priority arbiter.

Owner chat always wins. Detect activity from the proxy heartbeat file and
owner lines in /root/nox/logs/proxy.log. After IDLE_MINUTES with no owner
chat, mark the machine idle so weight/knowledge work may run.

Honesty / safety:
- Do NOT flip 8098 GPU profiles per message (restart is ~5-7 min).
- Keep chat-both until weight training is explicitly armed.
- Do NOT SIGSTOP llama-server, 8098, Engram, or CUDA trainers (deadlock risk).
  Trainers must check TRAIN_PAUSE_REQUEST.flag each step (already supported
  by t131u trainer).
- This process never starts weight training by itself.
- Never touches Engram pid or teacher restore.
"""
from __future__ import annotations

import json
import os
import signal
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

MADRID = timezone(timedelta(hours=1))  # Europe/Madrid winter (CET)
ROOT = Path("/root/nox")
PRIO = ROOT / "state" / "priority"
LOG = Path("/root/nox/logs/nox_priority_arbiter.log")
PROXY_LOG = ROOT / "logs" / "proxy.log"
HEARTBEAT = PRIO / "LAST_OWNER_CHAT"
MODE = PRIO / "MODE"
CHAT_ACTIVE = PRIO / "CHAT_ACTIVE"
TRAIN_PAUSE = PRIO / "TRAIN_PAUSE"
KNOWLEDGE_PAUSE = PRIO / "KNOWLEDGE_PAUSE"
STATUS = PRIO / "status.json"
IDLE_MINUTES_FILE = PRIO / "IDLE_MINUTES"
TRAIN_PAUSE_COMPAT = ROOT / "state" / "TRAIN_PAUSE_REQUEST.flag"
TRAINING_ARMED = PRIO / "TRAINING_ARMED"
PAUSED_PIDS = PRIO / "paused_knowledge_pids.json"

# CPU-only knowledge indexers that may be SIGSTOP/CONT. Never llama-server.
KNOWLEDGE_NAME_PARTS = (
    "s03_index",
    "s03_embed_backfill",
    "nox_s03_embed",
    "textbook_embed",
    "knowledge_index",
    "infinite_memory_index",
)

OWNER_LOG_MARKERS = (
    "chat_timing ",
    "chat_ttft ",
    "chat_login_ok ",
    "s03_owner_stream_postflight",
)

POLL_SEC = 1.0
DEFAULT_IDLE_MIN = 3


def now_madrid() -> datetime:
    return datetime.now(MADRID)


def iso(dt: datetime | None = None) -> str:
    return (dt or now_madrid()).strftime("%Y-%m-%d %H:%M:%S %Z")


def log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{iso()}] {msg}\n"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def idle_minutes() -> float:
    try:
        return max(0.5, float(IDLE_MINUTES_FILE.read_text().strip()))
    except Exception:
        return DEFAULT_IDLE_MIN


def parse_ts(s: str) -> datetime | None:
    s = (s or "").strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S %z",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(MADRID)
        except ValueError:
            continue
    return None


def proxy_log_last_owner() -> datetime | None:
    """Read the tail of proxy.log for the latest owner-chat marker."""
    try:
        if not PROXY_LOG.exists():
            return None
        size = PROXY_LOG.stat().st_size
        with PROXY_LOG.open("rb") as f:
            f.seek(max(0, size - 128_000))
            data = f.read().decode("utf-8", "replace")
    except Exception:
        return None
    last = None
    for line in data.splitlines():
        if not any(m in line for m in OWNER_LOG_MARKERS):
            continue
        # "2026-11-17 15:19:39 +0000 chat_timing ..."
        parts = line.split()
        if len(parts) >= 3 and parts[2].startswith("+") or (len(parts) >= 3 and parts[2].startswith("-")):
            dt = parse_ts(f"{parts[0]} {parts[1]} {parts[2]}")
        else:
            dt = parse_ts(f"{parts[0]} {parts[1]}") if len(parts) >= 2 else None
        if dt and (last is None or dt > last):
            last = dt
    return last


def heartbeat_last() -> datetime | None:
    try:
        return parse_ts(HEARTBEAT.read_text(encoding="utf-8"))
    except Exception:
        return None


def latest_owner_activity() -> datetime | None:
    cands = [d for d in (heartbeat_last(), proxy_log_last_owner()) if d]
    return max(cands) if cands else None


def set_pause_flags(active: bool) -> None:
    write_text(TRAIN_PAUSE, "1\n" if active else "0\n")
    write_text(KNOWLEDGE_PAUSE, "1\n" if active else "0\n")
    write_text(CHAT_ACTIVE, "1\n" if active else "0\n")
    write_text(MODE, "ACTIVE\n" if active else "IDLE\n")
    if active:
        write_text(TRAIN_PAUSE_COMPAT, f"{iso()} arbiter chat-active\n")
    else:
        try:
            if TRAIN_PAUSE_COMPAT.exists():
                TRAIN_PAUSE_COMPAT.unlink()
        except Exception as e:
            log(f"clear TRAIN_PAUSE_REQUEST failed: {type(e).__name__}")


def list_knowledge_pids() -> list[int]:
    pids = []
    try:
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            try:
                cmd = (entry / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace")
            except Exception:
                continue
            if "llama-server" in cmd or "engram_memfd" in cmd or "nox_priority_arbiter" in cmd:
                continue
            if any(part in cmd for part in KNOWLEDGE_NAME_PARTS):
                pids.append(int(entry.name))
    except Exception:
        pass
    return pids


def sig_knowledge(pause: bool) -> list[int]:
    """SIGSTOP/CONT only allowlisted CPU knowledge indexers, never llama-server."""
    changed = []
    stored = []
    if PAUSED_PIDS.exists():
        try:
            stored = json.loads(PAUSED_PIDS.read_text())
        except Exception:
            stored = []
    targets = set(list_knowledge_pids() + [int(x) for x in stored if str(x).isdigit()])
    for pid in sorted(targets):
        try:
            os.kill(pid, signal.SIGSTOP if pause else signal.SIGCONT)
            changed.append(pid)
        except ProcessLookupError:
            continue
        except PermissionError as e:
            log(f"sig {pid} {type(e).__name__}")
        except Exception as e:
            log(f"sig {pid} {type(e).__name__}")
    write_text(PAUSED_PIDS, json.dumps(changed if pause else [], indent=2))
    return changed


def cgroup_free_gib() -> float | None:
    try:
        cur = int(Path("/sys/fs/cgroup/memory.current").read_text())
        mx = int(Path("/sys/fs/cgroup/memory.max").read_text())
        return (mx - cur) / 1024**3
    except Exception:
        return None


def write_status(active: bool, last: datetime | None, idle_for: float, extra: dict) -> None:
    payload = {
        "cycle": "t162u",
        "mode": "ACTIVE" if active else "IDLE",
        "when_madrid": iso(),
        "last_owner_chat": iso(last) if last else None,
        "idle_for_min": round(idle_for, 3),
        "idle_threshold_min": idle_minutes(),
        "train_pause": active,
        "knowledge_pause": active,
        "training_armed": TRAINING_ARMED.exists() and TRAINING_ARMED.read_text().strip() in {"1", "true", "yes"},
        "cgroup_free_gib": None if cgroup_free_gib() is None else round(cgroup_free_gib(), 2),
        "weight_training": "not_started_by_arbiter",
        "profile_policy": "do_not_flip_per_message; chat-both until training is armed; chat-gpu0 only on one planned restart when training actually starts",
        **extra,
    }
    write_text(STATUS, json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> None:
    PRIO.mkdir(parents=True, exist_ok=True)
    if not IDLE_MINUTES_FILE.exists():
        write_text(IDLE_MINUTES_FILE, f"{DEFAULT_IDLE_MIN}\n")
    log("arbiter start")
    last_mode = None
    while True:
        try:
            last = latest_owner_activity()
            now = now_madrid()
            if last is None:
                idle_for = 1e9
                active = False
            else:
                idle_for = (now - last).total_seconds() / 60.0
                active = idle_for < idle_minutes()
            set_pause_flags(active)
            changed = sig_knowledge(active)
            extra = {"knowledge_pids_signaled": changed}
            if last_mode is None or last_mode != active:
                log(f"mode={'ACTIVE' if active else 'IDLE'} last={iso(last) if last else 'none'} idle_min={idle_for if idle_for < 1e8 else 'inf'} sig={changed}")
                last_mode = active
            write_status(active, last, 0 if idle_for > 1e8 else idle_for, extra)
        except Exception as e:
            log(f"loop error {type(e).__name__}: {e}")
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
