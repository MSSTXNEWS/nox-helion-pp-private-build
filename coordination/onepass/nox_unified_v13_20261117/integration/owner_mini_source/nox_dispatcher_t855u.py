#!/usr/bin/env python3
"""Permanent NOX dispatcher (t855u/t857u/t858u/t859u).

Work-stealing task runner over /root/nox/state/dispatcher/queue.jsonl + state.json.
Lanes are preferences only; idle workers steal any ready task. Only real
dependencies and resource locks block. Autostarts under supervisor.

Never touches a trainer mid-step, never changes chat -np 6, never deletes
without a verified copy or regeneration path, never prints secrets.
Identity→swap cannot silently loop on OOM (max 3 environmental retries).
"""
from __future__ import annotations

import hashlib, json, os, re, shutil, signal, subprocess, sys, threading, time, traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, "/root/nox/scripts")
try:
    import nox_journal as journal
except Exception:
    journal = None

# NOX_OWNER_MENTOR_PATCH_V1
import owner_dispatcher_mentor as owner_mentor
from owner_component_tasks import run_component_task

MSK = timezone(timedelta(hours=3))
ROOT = Path("/root/nox")
DSTATE = ROOT / "state" / "dispatcher"
QUEUE = DSTATE / "queue.jsonl"
STATE = DSTATE / "state.json"
EVENTS = DSTATE / "events.jsonl"
STATUS = ROOT / "status" / "dispatcher_t855u.json"
LIVE = ROOT / "state" / "NEW_MODEL_LIVE.json"
LOG = ROOT / "logs" / "dispatcher_t855u.log"
DISTILL = ROOT / "distill" / "queue" / "accepted_20261113.jsonl"
Q4 = ROOT / "progress_pull_t784u" / "gguf" / "nox36-mix_final_pref-Q4_K_M.gguf"
Q8 = ROOT / "progress_pull_t784u" / "gguf" / "nox36-mix_final_pref-q8_0.gguf"
IDJSON = ROOT / "progress_pull_t784u" / "eval" / "IDENTITY_3of3.json"
ID_OOM = ROOT / "progress_pull_t784u" / "eval" / "IDENTITY_3of3.fail_oom_t855u.json"
SWAP_DONE = ROOT / "state" / "council" / "SWAP_35B_t845u.done"
OWNER_ACTIVE = ROOT / "state" / "scheduler" / "OWNER_ORDER_ACTIVE.json"
OWNER_DONE = ROOT / "state" / "scheduler" / "OWNER_ORDER_DONE.flag"
IDENTITY_NEED = ROOT / "state" / "scheduler" / "IDENTITY_NEEDS_GPU1"
YIELD_FLAG = ROOT / "state" / "scheduler" / "YIELD_FOR_OWNER"
CLI = Path("/root/nox/bin/llama-cli")
START_CHAT = ROOT / "scripts" / "start_chat_8081.sh"
ROLLBACK = ROOT / "scripts" / "rollback_chat_s1.sh"
YAML = ROOT / "config" / "train_qlora_35b_t848u.yaml"
PUBLIC = "http://166.113.48.41:11555/chat"
MAX_OOM_RETRIES = 3
def _load_workers():
    # Owner selected six task runners; tuner and missing config cannot expand it.
    return 6
WORKERS = _load_workers()
AGENT_STATUS = ROOT / "status" / "agents_t856u.json"
# Lane names are preferences only; workers steal any ready task.
LANE_PREFS = ["owner_order", "owner_order", "training", "agent_distill", "downloads", "background"]
_wstate = {i: {"id": f"nox-agent-{i+1:02d}", "lane_preference": LANE_PREFS[i],
               "current_task": None, "tasks_done": 0, "tok_s": 0.0, "status": "idle"}
           for i in range(WORKERS)}
_wlock = threading.Lock()

CLASSES = ["chat", "owner_order", "watchdog", "gguf_identity", "agent_distill", "training", "downloads", "background"]
PRIO = {c: i for i, c in enumerate(CLASSES)}
LOCKS = {"gpu0": threading.Lock(), "gpu1": threading.Lock(), "disk": threading.Lock(), "chat_swap": threading.Lock()}
_qlock = threading.RLock()
SECRET_RE = re.compile(r"(?i)(gh[_p]_|github_pat_|hf_|sk-[A-Za-z0-9]|api[_-]?key|token|password|secret)\s*[:=]\s*\S+")


def now_msk() -> str:
    return datetime.now(MSK).strftime("%Y-%m-%d %H:%M:%S Europe/Moscow (UTC+3)")


def log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{now_msk()}] {msg}"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def redact(s: str) -> str:
    return owner_mentor.redact(s)


def atomic_write(path: Path, obj: Any) -> None:
    owner_mentor.atomic_json(path, obj)


def disk_free_gb() -> float:
    st = os.statvfs("/")
    return st.f_bavail * st.f_frsize / (1024 ** 3)


def vram() -> list[dict]:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index,memory.used,memory.total,utilization.gpu",
             "--format=csv,noheader,nounits"], text=True, timeout=5)
    except Exception:
        return []
    gpus = []
    for line in out.strip().splitlines():
        i, used, total, util = [x.strip() for x in line.split(",")]
        used, total = float(used), float(total)
        gpus.append({"index": int(i), "used_mib": used, "total_mib": total,
                     "pct": used / total if total else 0, "util": float(util)})
    return gpus


def gpu1_used() -> float:
    for g in vram():
        if g["index"] == 1:
            return g["used_mib"]
    return 0.0


def pgrep(pattern: str) -> list[int]:
    pids = []
    try:
        out = subprocess.check_output(["pgrep", "-f", pattern], text=True)
        for ln in out.split():
            try:
                pids.append(int(ln))
            except ValueError:
                pass
    except subprocess.CalledProcessError:
        pass
    return pids


def ev(kind: str, **kw):
    rec = {"ts": now_msk(), "kind": kind, **kw}
    EVENTS.parent.mkdir(parents=True, exist_ok=True)
    with EVENTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def learn(ok: bool, task_id: str, what: str, evidence: Any, fix: str = "", task=None) -> None:
    try:
        row = owner_mentor.record_experience(ok, task or {"id": task_id}, what, evidence, fix, DISTILL)
        verified = bool(row.get("verification"))
        ev("learn", ok=ok, task=task_id, verified=verified, partition=row.get("partition"))
        if journal:
            fn = journal.log_improvement if verified else journal.log_error
            fn(source="dispatcher_t855u", what=owner_mentor.redact(what),
               evidence=owner_mentor.clean(row), root_cause="" if verified else "unverified_result",
               fix=owner_mentor.redact(fix), verified=verified, impact="dispatcher")
    except Exception as exc:
        ev("experience_journal_blocked", task=task_id, error=type(exc).__name__)


# ---------- queue state ----------
def load_state() -> dict:
    st = {"tasks": {}, "updated": now_msk()}
    if STATE.exists():
        try:
            st = json.loads(STATE.read_text())
        except Exception:
            pass
    if QUEUE.exists():
        for line in QUEUE.read_text().splitlines():
            if not line.strip():
                continue
            try:
                t = json.loads(line)
            except Exception:
                continue
            tid = t.get("id")
            if tid and tid not in st["tasks"]:
                st["tasks"][tid] = t
    return st


def _task_public(t: dict) -> dict:
    return {k: v for k, v in t.items() if not k.startswith("_")}

def save_state(st: dict) -> None:
    # Snapshot and atomic replace share the same reentrant claim lock.
    with _qlock:
        owner_mentor.require_dispatcher_writer(globals())
        st["updated"] = now_msk()
        clean = {"updated": st.get("updated"), "tasks": {tid: _task_public(t) for tid, t in (st.get("tasks") or {}).items()}}
        atomic_write(STATE, clean)
        lines = [json.dumps(t, ensure_ascii=False) for t in clean["tasks"].values()]
        tmp = QUEUE.with_suffix(".jsonl.tmp")
        tmp.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        tmp.replace(QUEUE)


def upsert(st: dict, task: dict) -> None:
    with _qlock:
        tid = task["id"]
        old = st["tasks"].get(tid, {})
        # Only an explicit reconciled reset may replay a previous claim.
        if old.get("status") in ("done", "running", "blocked") and task.get("status") != "reset":
            return
        merged = {**old, **task}
        if merged.get("status") == "reset":
            merged["status"] = "pending"
        st["tasks"][tid] = merged


def seed_if_needed(st: dict) -> None:
    if st["tasks"]:
        # still allow reconciling pipeline facts
        reconcile(st)
        return
    def T(id, cls, prio, deps, handler, title, **kw):
        return {"id": id, "class": cls, "priority": prio, "deps": deps, "handler": handler,
                "title": title, "status": kw.get("status", "pending"),
                "lane": kw.get("lane", cls), "locks": kw.get("locks", []),
                "retries": 0, "max_retries": kw.get("max_retries", 3),
                "timeout_sec": kw.get("timeout_sec", 1800),
                "note": kw.get("note", ""), "source": kw.get("source", "pipeline"),
                "result": kw.get("result")}

    seeds = [
        T("p0.q4_done", "gguf_identity", 0, [], "wait_q4", "Дождаться Q4_K_M", timeout_sec=7200),
        T("p0.verify_q4", "gguf_identity", 0, ["p0.q4_done"], "verify_q4", "Проверить Q4 (магия GGUF, размер)"),
        T("p0.delete_q8", "gguf_identity", 0, ["p0.verify_q4"], "delete_q8", "Удалить q8_0 после проверки Q4 (регенерируется из merged_hf)"),
        T("p0.identity", "gguf_identity", 0, ["p0.verify_q4"], "identity",
          "Identity 3/3 на GPU1 (OOM → yield учителей, --n-cpu-moe, макс. 3 попытки)",
          locks=["gpu1"], max_retries=3, timeout_sec=1200),
        T("p0.hot_swap", "gguf_identity", 0, ["p0.identity"], "hot_swap",
          "Горячая замена чата на 35B GPU0, -np 6, VRAM≤92%, откат S1-L05",
          locks=["gpu0", "chat_swap"], timeout_sec=600),
        T("p0.write_live", "gguf_identity", 0, ["p0.hot_swap"], "write_live", "Записать NEW_MODEL_LIVE.json"),
        T("p0.start_qlora", "training", 3, ["p0.write_live"], "start_qlora",
          "QLoRA 35B по train_qlora_35b_t848u.yaml (не старый train_worm)",
          locks=["gpu0"], timeout_sec=0, max_retries=20),
        T("p0.holdout_gate", "training", 3, ["p0.start_qlora"], "holdout_gate",
          "Holdout-гейт адаптера (identity 3/3 + команды владельца)", timeout_sec=0),
        T("p0.merge_gated", "training", 3, ["p0.holdout_gate"], "merge_gated",
          "Слияние только гейтованных адаптеров (mergekit)", timeout_sec=0),
        T("p0.new_gguf", "gguf_identity", 0, ["p0.merge_gated"], "new_gguf",
          "Новый GGUF из слитой модели", timeout_sec=0),
        T("p0.identity_cycle", "gguf_identity", 0, ["p0.new_gguf"], "identity",
          "Identity 3/3 нового GGUF и замена", timeout_sec=0),
        T("ensure.downloads", "downloads", 4, [], "ensure_downloads",
          "Непрерывные загрузки nox-downloads-t802u (пауза диск<12ГБ или VRAM>92%)"),
        T("ensure.scheduler", "background", 5, [], "ensure_scheduler", "Планировщик приоритетов с owner_order"),
        T("ensure.offload", "background", 5, [], "ensure_offload", "Червь разгрузки диска t850u, пол 12 ГБ"),
        T("ensure.tuner", "background", 5, [], "ensure_program",
          "nox-agent-tuner каждые 30 мин", note="nox-agent-tuner-t858u"),
        T("ensure.integrator", "background", 5, [], "ensure_program",
          "nox-agent-integrator ставит новое и пишет INVENTORY", note="nox-agent-integrator-t859u"),
        T("ensure.architect", "background", 5, [], "ensure_program",
          "nox-agent-architect планирует пайплайн каждые 30 мин", note="nox-agent-architect-t859u"),
        T("p1.agent_tools", "agent_distill", 1, [], "track",
          "Инструменты агента в чате (t845u) уже живые — поддерживать и дистиллировать",
          status="done", source="HANDOFF_t845u_agent"),
        T("p2.persona_memory", "background", 2, [], "track",
          "Память/личность/эмоции t826u-t827u, журнал t846u", source="OWNER_RULE_t845u"),
        T("p3.server_stack", "background", 3, [], "track",
          "Стек t848u (install_python_t848u, когда диск и venv_v100 готовы)", source="t848u"),
        T("p5.downloads_queue", "downloads", 4, ["ensure.downloads"], "track",
          "Очередь DOWNLOAD_QUEUE_t818u + OWNER_TASKS_t849u под планировщиком"),
        T("p6.pages", "background", 6, [], "track", "Страницы t812u/t813u/t816u — после ядра агента"),
        T("p6.v35", "background", 6, [], "track", "V35 знания — после ядра"),
        T("p6.photo_video", "background", 6, [], "track", "Фото/видео t817u — после ядра"),
        T("p6.ram_models", "background", 6, [], "track", "Большие модели в RAM t831u — после ядра"),
        T("p6.backup_drive", "background", 5, [], "track", "Бэкап на Drive каждые 6ч"),
        T("arch.eval_gates", "training", 3, ["p0.write_live"], "track",
          "Постоянные eval-гейты и регрессия качества (архитектор)", source="t859u"),
        T("arch.data_quality", "agent_distill", 2, [], "track",
          "Фильтрация качества данных / дедуп (архитектор)", source="t859u"),
        T("arch.backups_rollback", "background", 5, [], "track",
          "Бэкапы, откат чата S1-L05, мониторинг, безопасность (архитектор)", source="t859u"),
    ]
    # fold remaining steps from handoffs if present
    for hf in [
        ROOT / "state/council/HANDOFF_t845u_agent.json",
        ROOT / "state/council/HANDOFF_t850u_offload.json",
        ROOT / "state/council/OWNER_TASKS_t849u.json",
    ]:
        if not hf.exists():
            continue
        try:
            doc = json.loads(hf.read_text())
        except Exception:
            continue
        for step in doc.get("remaining_steps_for_dispatcher") or doc.get("what_nox_does_next") or []:
            if isinstance(step, str):
                sid = "handoff." + hashlib.sha1(step.encode()).hexdigest()[:10]
                seeds.append(T(sid, "background", 5, [], "track", step[:200], source=hf.name))
            elif isinstance(step, dict):
                sid = step.get("id") or ("handoff." + hashlib.sha1(json.dumps(step, ensure_ascii=False).encode()).hexdigest()[:10])
                seeds.append(T(sid, "background", 5, [], "track",
                               step.get("title") or step.get("id") or str(step)[:200], source=hf.name))
        for group, items in (doc.get("tasks") or {}).items() if isinstance(doc.get("tasks"), dict) else []:
            prio = {"A_training_speed_quality_depth": 3, "B_server_admin_overclock_scheduling": 3,
                    "C_alive": 2, "D_work_in_nox": 1}.get(group, 5)
            cls = "training" if group.startswith("A") else ("background" if group.startswith("B") else "agent_distill")
            for it in items:
                sid = "t849u." + hashlib.sha1((group + it).encode()).hexdigest()[:12]
                seeds.append(T(sid, cls, prio, [], "track", it[:220], source="OWNER_TASKS_t849u"))
    for s in seeds:
        upsert(st, s)
    reconcile(st)


def identity_is_oom(doc: dict) -> bool:
    if not doc:
        return False
    if doc.get("identity_pass"):
        return False
    blob = json.dumps(doc, ensure_ascii=False)
    keys = ("unable to allocate CUDA", "failed to load model", "CUDA out of memory",
            "out of memory", "server exited before becoming ready")
    if any(k.lower() in blob.lower() for k in keys):
        return True
    items = doc.get("items") or []
    if items and all((it.get("rc") not in (0, None) or not (it.get("text") or "").strip()
                      or "Loading model" in (it.get("text") or "")) and not it.get("ident_ok")
                     for it in items):
        # no real answers
        if all(it.get("rc") != 0 for it in items):
            return True
    return False


def identity_real_fail(doc: dict) -> bool:
    if not doc or doc.get("identity_pass"):
        return False
    if identity_is_oom(doc):
        return False
    items = doc.get("items") or []
    # at least one real generated answer that is not NOX / is Qwen
    real = [it for it in items if it.get("rc") == 0 and len(re.sub(r".*Loading model.*", "", it.get("text") or "", flags=re.S)) > 20]
    return bool(real) and not doc.get("identity_pass")


def reconcile(st: dict) -> None:
    """Mark already-finished pipeline steps without re-running them."""
    def done(tid, note, result=None):
        t = st["tasks"].get(tid)
        if not t or t.get("status") in ("running", "blocked"):
            return
        if t.get("status") != "done":
            t["status"] = "done"
            t["finished_at"] = now_msk()
            t["note"] = note
            if result is not None:
                t["result"] = result

    if Q4.exists() and Q4.stat().st_size > 10_000_000_000 and not pgrep("llama-quantize"):
        done("p0.q4_done", f"Q4 ready {Q4.stat().st_size} bytes")
        if owner_mentor.verify_success({"handler": "verify_q4"}):
            done("p0.verify_q4", f"size={Q4.stat().st_size} stable, quantize not running")
    if not Q8.exists() and Q4.exists() and Q4.stat().st_size > 10_000_000_000:
        done("p0.delete_q8", "q8 already absent; Q4 present (regenerable from merged_hf)")
    if IDJSON.exists():
        try:
            doc = json.loads(IDJSON.read_text())
        except Exception:
            doc = {}
        if doc.get("identity_pass") and doc.get("identity_ok") == 3:
            done("p0.identity", "identity 3/3 pass", {"identity_pass": True, "ts": doc.get("ts_msk")})
        elif identity_is_oom(doc) and (st["tasks"].get("p0.identity") or {}).get("status") not in ("running", "blocked"):
            t = st["tasks"].get("p0.identity") or {}
            t.update({"id": "p0.identity", "status": "pending",
                      "note": "previous identity was CUDA OOM, will retry (not a personality fail)",
                      "oom_retries": int(t.get("oom_retries") or 0)})
            st["tasks"]["p0.identity"] = t
    if SWAP_DONE.exists() and "swapped_35b_verified" in SWAP_DONE.read_text(errors="replace"):
        done("p0.hot_swap", SWAP_DONE.read_text().strip())
        # live file may still be missing
        if LIVE.exists():
            done("p0.write_live", str(LIVE))


# ---------- handlers ----------
def h_wait_q4(task):
    if Q4.exists() and Q4.stat().st_size > 10_000_000_000 and not pgrep("llama-quantize"):
        return True, f"Q4 {Q4.stat().st_size} bytes"
    if pgrep("llama-quantize"):
        return "wait", "quantize still running"
    if not Q4.exists() or Q4.stat().st_size < 10_000_000_000:
        if Q8.exists():
            return "wait", "Q4 missing, q8 present — another executor should quantize; not starting a second"
        return False, "Q4 missing and q8 missing"
    return "wait", "Q4 growing"


def h_verify_q4(task):
    if not Q4.exists():
        return False, "Q4 missing"
    sz = Q4.stat().st_size
    if sz < 10_000_000_000:
        return False, f"Q4 too small {sz}"
    with Q4.open("rb") as _header:
        magic = _header.read(4)
    if magic not in (b"GGUF", b"gguf"):
        # GGUF magic is GGUF
        if magic != b"GGUF":
            return False, f"bad magic {magic!r}"
    time.sleep(2)
    if Q4.stat().st_size != sz:
        return "wait", "size changed"
    return True, {"bytes": sz, "magic": "GGUF"}


def h_delete_q8(task):
    return "wait", "HOLD: destructive removal requires independently verified PC and Drive backups"


def _stop_gpu1_teachers():
    IDENTITY_NEED.parent.mkdir(parents=True, exist_ok=True)
    IDENTITY_NEED.write_text(now_msk() + "\n")
    try:
        subprocess.run(["supervisorctl", "stop", "nox-teacher-serve-t811u"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    except Exception:
        pass
    # kill leftover GPU1 llama (not 8081)
    try:
        out = subprocess.check_output(["ss", "-tlnp"], text=True, timeout=5)
    except Exception:
        out = ""
    for port in (8083, 8084, 8086, 8096):
        m = re.search(rf":{port}\b.*pid=(\d+)", out)
        if m:
            pid = int(m.group(1))
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass
    for _ in range(20):
        if gpu1_used() < 4096:
            return True
        time.sleep(1)
    return gpu1_used() < 8192


def _restore_teachers():
    try:
        if IDENTITY_NEED.exists():
            IDENTITY_NEED.unlink()
    except Exception:
        pass
    try:
        _nox_owner_start_service("nox-teacher-serve-t811u",
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    except Exception:
        pass
    try:
        subprocess.run(["supervisorctl", "start", "nox-vram-guard-t829u"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
    except Exception:
        pass


def _run_identity_once() -> dict:
    prompts = [
        {"id": "who", "prompt": "Кто ты? Представься коротко."},
        {"id": "name", "prompt": "Как тебя зовут и кто тебя создал?"},
        {"id": "memory", "prompt": "Что ты обо мне помнишь? Ответь кратко."},
    ]
    recs = []
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": "1"}
    for p in prompts:
        t0 = time.time()
        proc = subprocess.run(
            [str(CLI), "-m", str(Q4), "-ngl", "99", "-c", "4096", "-n", "160",
             "--temp", "0.2", "--top-p", "0.9", "--seed", "7",
             "--jinja", "--no-display-prompt", "--log-disable",
             "--n-cpu-moe", "8", "-p", p["prompt"]],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, timeout=300,
        )
        text = proc.stdout or ""
        mentions_nox = bool(re.search(r"\bNOX\b", text, re.I))
        mentions_qwen = bool(re.search(r"\bQwen\b|Alibaba", text, re.I))
        recs.append({**p, "text": text[-2000:], "seconds": round(time.time() - t0, 2),
                     "mentions_nox": mentions_nox, "mentions_qwen_or_alibaba": mentions_qwen,
                     "ident_ok": mentions_nox and not mentions_qwen,
                     "rc": proc.returncode, "stderr_tail": (proc.stderr or "")[-500:]})
    ok = sum(1 for r in recs if r["ident_ok"])
    doc = {"ts_msk": now_msk(), "gguf": str(Q4),
           "gguf_bytes": Q4.stat().st_size if Q4.exists() else 0,
           "identity_ok": ok, "identity_n": 3, "identity_pass": ok == 3, "items": recs}
    IDJSON.parent.mkdir(parents=True, exist_ok=True)
    IDJSON.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return doc


def h_identity(task):
    # already passed
    if IDJSON.exists():
        try:
            doc = json.loads(IDJSON.read_text())
        except Exception:
            doc = {}
        if doc.get("identity_pass") and doc.get("identity_ok") == 3:
            return True, {"identity_pass": True, "ts": doc.get("ts_msk")}
        if identity_real_fail(doc):
            return False, {"identity_pass": False, "reason": "real_personality_fail", "ts": doc.get("ts_msk")}
        if identity_is_oom(doc):
            # bak and retry, do not loop silently
            oom_n = int(task.get("oom_retries") or 0)
            bak = ID_OOM if not ID_OOM.exists() else IDJSON.with_suffix(f".fail_oom_{oom_n}.json")
            try:
                shutil.copy2(IDJSON, bak)
            except Exception:
                pass
            try:
                IDJSON.unlink()
            except Exception:
                pass
            task["oom_retries"] = oom_n + 1
            if oom_n + 1 > MAX_OOM_RETRIES:
                gave = IDJSON.parent / "IDENTITY_OOM_GAVE_UP.json"
                gave.write_text(json.dumps({"ts": now_msk(), "retries": oom_n + 1,
                                            "reason": "CUDA OOM after max retries; not looping"}, indent=2), encoding="utf-8")
                return False, {"reason": "oom_gave_up", "retries": oom_n + 1}
            log(f"identity previous was OOM, retry {oom_n + 1}/{MAX_OOM_RETRIES}")
    # if watch_swap / identity already running, wait (don't duplicate)
    if pgrep("watch_swap_35b_t845u") or pgrep("llama-cli .*nox36-mix_final_pref"):
        return "wait", "identity/swap already in flight"
    if not Q4.exists():
        return False, "Q4 missing"
    try:
        if not _stop_gpu1_teachers():
            used = gpu1_used()
            if used >= 20000:
                return "wait", f"GPU1 still {used} MiB, cannot identity yet"
        doc = _run_identity_once()
        if doc.get("identity_pass"):
            return True, {"identity_pass": True, "ts": doc.get("ts_msk")}
        if identity_is_oom(doc):
            task["oom_retries"] = int(task.get("oom_retries") or 0) + 1
            if task["oom_retries"] > MAX_OOM_RETRIES:
                return False, {"reason": "oom_gave_up", "retries": task["oom_retries"]}
            return "wait", f"OOM retry {task['oom_retries']}/{MAX_OOM_RETRIES}"
        return False, {"identity_pass": False, "reason": "personality_or_empty"}
    finally:
        _restore_teachers()


def _chat_health() -> bool:
    try:
        r = subprocess.run(["curl", "-sf", "--max-time", "3", "http://127.0.0.1:8081/health"],
                           stdout=subprocess.PIPE, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def h_hot_swap(task):
    if SWAP_DONE.exists() and "swapped_35b_verified" in SWAP_DONE.read_text(errors="replace"):
        return True, SWAP_DONE.read_text().strip()
    if not IDJSON.exists():
        return False, "no identity json"
    doc = json.loads(IDJSON.read_text())
    if not doc.get("identity_pass"):
        return False, "refuse swap: identity not 3/3 (will not half-swap)"
    # if watcher still running, let it finish
    if pgrep("watch_swap_35b_t845u"):
        return "wait", "watch_swap in flight"
    # stop GPU0 teacher :8085 only
    try:
        out = subprocess.check_output(["ss", "-tlnp"], text=True, timeout=5)
        m = re.search(r":8085\b.*pid=(\d+)", out)
        if m:
            os.kill(int(m.group(1)), signal.SIGTERM)
            time.sleep(2)
    except Exception:
        pass
    r = subprocess.run(["bash", str(START_CHAT), "35b", str(Q4), "16384"],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120)
    if r.returncode != 0:
        subprocess.run(["bash", str(ROLLBACK)], timeout=120)
        return False, "start 35b failed, rolled back S1-L05: " + (r.stdout or "")[-400:]
    ok = False
    for _ in range(40):
        if _chat_health():
            ok = True
            break
        time.sleep(2)
    if not ok:
        subprocess.run(["bash", str(ROLLBACK)], timeout=120)
        return False, "health failed, rolled back S1-L05"
    # live verify
    pry = subprocess.run(
        ["curl", "-sf", "--max-time", "90", "http://127.0.0.1:8081/v1/chat/completions",
         "-H", "Content-Type: application/json",
         "-d", json.dumps({"messages": [{"role": "user", "content": "Кто ты? Представься коротко."}],
                           "temperature": 0.2, "max_tokens": 120, "stream": False})],
        stdout=subprocess.PIPE, text=True, timeout=100)
    try:
        d = json.loads(pry.stdout or "{}")
        text = (((d.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
    except Exception:
        text = ""
    if not re.search(r"NOX", text, re.I) or re.search(r"Qwen|Alibaba", text, re.I):
        subprocess.run(["bash", str(ROLLBACK)], timeout=120)
        return False, f"verify failed, rolled back S1-L05 text={text[:200]}"
    # VRAM cap
    g0 = next((g for g in vram() if g["index"] == 0), None)
    if g0 and g0["pct"] > 0.92:
        subprocess.run(["bash", str(ROLLBACK)], timeout=120)
        return False, f"VRAM {g0['pct']:.3f} > 0.92, rolled back"
    SWAP_DONE.write_text(f"swapped_35b_verified {now_msk()}\n")
    return True, {"answer": text[:400], "vram": g0, "public": PUBLIC}


def h_write_live(task):
    ident = {}
    if IDJSON.exists():
        try:
            ident = json.loads(IDJSON.read_text())
        except Exception:
            pass
    sha = ""
    sha_path = Path(str(Q4) + ".sha256")
    part = Path(str(Q4) + ".sha256.partial")
    if sha_path.exists():
        sha = sha_path.read_text().split()[0]
    elif part.exists():
        txt = part.read_text().strip()
        if txt and " " in txt and Path(txt.split()[-1]).exists():
            sha = txt.split()[0]
            sha_path.write_text(txt + "\n")
    g0 = next((g for g in vram() if g["index"] == 0), None)
    answers = []
    for it in ident.get("items") or []:
        answers.append({"id": it.get("id"), "ok": it.get("ident_ok"), "text": (it.get("text") or "")[-500:]})
    # include live verify if present
    live_ans = None
    if SWAP_DONE.exists():
        live_ans = "see swap log / verify"
    try:
        pry = subprocess.run(
            ["curl", "-sf", "--max-time", "60", "http://127.0.0.1:8081/v1/chat/completions",
             "-H", "Content-Type: application/json",
             "-d", json.dumps({"messages": [{"role": "user", "content": "Кто ты? Представься коротко."}],
                               "temperature": 0.2, "max_tokens": 80, "stream": False})],
            stdout=subprocess.PIPE, text=True, timeout=70)
        d = json.loads(pry.stdout or "{}")
        live_ans = (((d.get("choices") or [{}])[0].get("message") or {}).get("content") or "")[:500]
    except Exception:
        pass
    doc = {
        "ts_msk": now_msk(),
        "model": str(Q4),
        "gguf_bytes": Q4.stat().st_size if Q4.exists() else 0,
        "sha256": sha or "pending_background_hash",
        "identity": {"pass": ident.get("identity_pass"), "ok": ident.get("identity_ok"),
                     "n": ident.get("identity_n"), "ts": ident.get("ts_msk")},
        "identity_answers": answers,
        "live_answer_kto_ty": live_ans,
        "chat": {"port": 8081, "np": 6, "jinja": True, "n_cpu_moe": 4, "ctx": 16384,
                 "gpu": 0, "vram": g0, "public": PUBLIC,
                 "rollback": "bash /root/nox/scripts/rollback_chat_s1.sh"},
        "swap_done": SWAP_DONE.read_text().strip() if SWAP_DONE.exists() else None,
        "current_gguf_symlink_still_s1_for_rollback": True,
    }
    atomic_write(LIVE, doc)
    return True, {"path": str(LIVE), "sha256": sha or "pending"}


def _torch_ok(py: str) -> bool:
    try:
        r = subprocess.run([py, "-c",
                            "import torch; print(torch.__version__); print(torch.cuda.get_device_capability(0) if torch.cuda.is_available() else '')"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
        out = r.stdout
        # reject 2.15+ without sm_70
        if "2.15" in out or "(7, 5)" in out and "2.14" not in out:
            # capability print is (7,0) on V100 if kernels work
            pass
        if r.returncode != 0:
            return False
        # venv_v100 is only ok after Volta build (2.14 or any that reports (7, 0) without warning-only)
        if "venv_v100" in py and "2.14" not in out:
            return False
        return "True" in out or "(7, 0)" in out or r.returncode == 0 and "torch" not in (r.stderr or "").lower()
    except Exception:
        return False



# NOX_OWNER_ADMISSION_GUARD_V1: invoked by the existing controller only.
def _nox_owner_maintenance_busy():
    import fcntl as _f, os as _o
    _p=ROOT / "state" / "owner_maintenance.lock"
    try: _fd=_o.open(_p,_o.O_RDONLY|_o.O_NOFOLLOW)
    except FileNotFoundError: return False
    except OSError: return True
    try:
        try: _f.flock(_fd,_f.LOCK_SH|_f.LOCK_NB)
        except BlockingIOError: return True
        return False
    finally: _o.close(_fd)

def _nox_owner_boost_active():
    import json as _json
    _p=ROOT/"state/task_boost_mode.json"
    if not _p.exists(): return False
    try: return _json.loads(_p.read_text()).get("enabled") is True
    except (ValueError,OSError,AttributeError): return True


# NOX_OWNER_SINGLE_TRAINER_PERMISSION_V1
def _nox_owner_training_allowed():
    import json as _json
    _p=ROOT/"state/task_boost_mode.json"
    try:
        if _p.is_symlink() or _p.stat().st_size>16000: return False
        _v=_json.loads(_p.read_text())
        return (_v.get("enabled") is True and _v.get("mode")=="TASK_BOOST"
                and _v.get("training_allowed") is True
                and _v.get("training_service")=="nox-train-volta-t866u")
    except (ValueError,OSError,AttributeError): return False

def _nox_owner_task_admitted(task):
    if _nox_owner_maintenance_busy(): return False
    if not _nox_owner_boost_active(): return True
    if task.get("class") in ("training","agent_distill","gguf_identity"): return False
    if any(_name in ("gpu0","gpu1","chat_swap") for _name in (task.get("locks") or [])): return False
    if task.get("handler") in ("start_qlora","merge_gated","new_gguf","hot_swap","exec_plan"): return False
    return True

def _nox_owner_admission_reason(name):
    if _nox_owner_maintenance_busy(): return "owner maintenance holds admissions"
    if (_nox_owner_boost_active()
            and not (name=="nox-train-volta-t866u" and _nox_owner_training_allowed())
            and name in ("nox-train-volta-t866u","nox-train-worm-t811u",
            "nox-distill-worm-t811u","nox-self-improve-t846u","nox-self-learning-loop","nox-teacher-serve-t811u",
            "nox-offload-t850u","nox-downloads-t802u","nox-watch-swap-t845u","nox-agent-architect-t859u","nox-agent-tuner-t858u")):
        return "TASK_BOOST reserves resources for owner tasks"
    if name in ("nox-train-volta-t866u","nox-train-worm-t811u"):
        if name=="nox-train-worm-t811u": return "superseded trainer stays disabled"
        _flags=(ROOT/"STOP",ROOT/"STOP.flag",ROOT/"stop.flag",ROOT/"state/STOP",
                ROOT/"state/TRAIN_HOLD.flag",ROOT/"state/TRAIN_PAUSE_REQUEST.flag")
        if any(_p.exists() for _p in _flags): return "owner training hold or pause"
    if name=="nox-teacher-serve-t811u" and (ROOT/"state/train_wants_gpu1").exists():
        return "training resource reservation"
    return None

def _nox_owner_start_service(name, **kwargs):
    _reason=_nox_owner_admission_reason(name)
    if _reason:
        return subprocess.CompletedProcess(["supervisorctl","start",name],125,_reason,"")
    return subprocess.run(["supervisorctl","start",name],**kwargs)

def h_start_qlora(task):
    _owner_block=_nox_owner_admission_reason("nox-train-volta-t866u")
    if _owner_block: return "wait",_owner_block
    # never start old train_worm
    if pgrep("train_worm_t811u"):
        return "wait", "a trainer is running — never attach mid-step"
    if not YAML.exists():
        return False, "yaml missing"
    if YIELD_FLAG.exists():
        return "wait", "owner_order yield flag set"
    # venv choice: prefer dedicated Volta venv; never wait forever on venv_v100 2.15.
    py = None
    volta = "/root/venv_volta/bin/python"
    if Path(volta).exists() and _torch_ok(volta):
        py = volta
    v100 = "/root/venv_v100/bin/python"
    if py is None and Path(v100).exists():
        r = subprocess.run([v100, "-c", "import torch; print(torch.__version__); print(','.join(torch.cuda.get_arch_list()) if torch.cuda.is_available() else '')"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20)
        ver = (r.stdout or "").strip()
        if r.returncode == 0 and "sm_70" in ver:
            py = v100
        else:
            # fall through; installer t866u builds venv_volta
            py = None
    if py is None:
        if Path(volta).exists():
            return "wait", "venv_volta present but arch check failed — installer/verify should fix"
        return "wait", "waiting for /root/venv_volta (sm_70); do not use torch without matching GPU arch"
    # don't start until chat is stable
    if not _chat_health():
        return "wait", "chat not healthy"
    # GPU0 is full with 35B (~89%). Training must use ZeRO-3 CPU offload and leftover VRAM only.
    # Do not steal chat. Leave pending until a launch script exists that honors the yaml and offload.
    launch = ROOT / "scripts" / "start_qlora_35b_t855u.sh"
    if not launch.exists():
        launch.write_text(
            "#!/bin/bash\n# Started only by dispatcher when venv + yaml + VRAM headroom allow.\n"
            "# NEVER start nox-train-worm-t811u (broken).\n"
            "set -euo pipefail\n"
            "export TZ=Europe/Moscow\n"
            "PY=${PY:-/root/venv_new/bin/python}\n"
            "LOG=/root/nox/logs/qlora_35b_t848u.log\n"
            "exec \"$PY\" -u /root/nox/scripts/train_qlora_35b_t848u.py "
            "--config /root/nox/config/train_qlora_35b_t848u.yaml >>\"$LOG\" 2>&1\n",
            encoding="utf-8")
        launch.chmod(0o755)
    # trainer script for 35B yaml may not exist yet
    trainer = ROOT / "scripts" / "train_qlora_35b_t848u.py"
    if not trainer.exists():
        return "wait", "train_qlora_35b_t848u.py not yet written by integrator; will retry"
    # Training lives on GPU1 via nox-train-volta-t866u (chat keeps GPU0).
    prog = "nox-train-volta-t866u"
    try:
        r = subprocess.run(["supervisorctl", "status", prog], stdout=subprocess.PIPE, text=True, timeout=8)
        if "RUNNING" in (r.stdout or ""):
            return True, (r.stdout or "").strip()
    except Exception:
        pass
    if Path("/etc/supervisor/conf.d/nox-train-volta-t866u.conf").exists() and py and "venv_volta" in str(py):
        subprocess.run(["supervisorctl", "start", prog], timeout=8)
        time.sleep(2)
        r2 = subprocess.run(["supervisorctl", "status", prog], stdout=subprocess.PIPE, text=True, timeout=8)
        if "RUNNING" in (r2.stdout or "") or "STARTING" in (r2.stdout or ""):
            return True, (r2.stdout or "").strip()
        return "wait", (r2.stdout or "started, recheck").strip()
    return "wait", "waiting for venv_volta + nox-train-volta-t866u program (GPU1, not GPU0 chat)"


def h_holdout_gate(task):
    best = ROOT / "lora" / "qlora_t811u" / "best_gated" / "GATED"
    alt = ROOT / "lora" / "qlora_t848u" / "best_gated" / "GATED"
    if best.exists() or alt.exists():
        return True, "gated adapter present"
    return "wait", "no gated adapter yet"


def h_merge_gated(task):
    if not (ROOT / "lora" / "qlora_t811u" / "best_gated" / "GATED").exists() and not (
            ROOT / "lora" / "qlora_t848u" / "best_gated" / "GATED").exists():
        return "wait", "no gated adapter — refuse merge"
    return "wait", "mergekit after holdout — waiting for gated ckpt"


def h_new_gguf(task):
    return "wait", "waiting for gated merge before new GGUF"


def h_ensure_downloads(task):
    _owner_block=_nox_owner_admission_reason('nox-downloads-t802u')
    if _owner_block: return "wait",_owner_block
    r = subprocess.run(["supervisorctl", "status", "nox-downloads-t802u"],
                       stdout=subprocess.PIPE, text=True, timeout=8)
    out = r.stdout or ""
    if "RUNNING" in out:
        return True, out.strip()
    subprocess.run(["supervisorctl", "start", "nox-downloads-t802u"], timeout=8)
    time.sleep(2)
    r2 = subprocess.run(["supervisorctl", "status", "nox-downloads-t802u"],
                        stdout=subprocess.PIPE, text=True, timeout=8)
    ok = "RUNNING" in (r2.stdout or "")
    return (True if ok else "wait"), (r2.stdout or r.stdout).strip()


def h_ensure_scheduler(task):
    if pgrep("nox_priority_scheduler.py"):
        return True, "scheduler running"
    # supervisor program may exist
    r = subprocess.run(["supervisorctl", "status", "nox-priority-scheduler"],
                       stdout=subprocess.PIPE, text=True, timeout=8)
    if "RUNNING" in (r.stdout or ""):
        return True, r.stdout.strip()
    subprocess.run(["supervisorctl", "start", "nox-priority-scheduler"], timeout=8)
    time.sleep(1)
    if pgrep("nox_priority_scheduler.py"):
        return True, "started"
    return "wait", "scheduler not running yet"


def h_ensure_offload(task):
    _owner_block=_nox_owner_admission_reason('nox-offload-t850u')
    if _owner_block: return "wait",_owner_block
    r = subprocess.run(["supervisorctl", "status", "nox-offload-t850u"],
                       stdout=subprocess.PIPE, text=True, timeout=8)
    if "RUNNING" in (r.stdout or ""):
        return True, (r.stdout or "").strip()
    subprocess.run(["supervisorctl", "start", "nox-offload-t850u"], timeout=8)
    return "wait", "started offload, recheck"


def h_ensure_program(task):
    _owner_block=_nox_owner_admission_reason(task.get("note") or "")
    if _owner_block: return "wait",_owner_block
    name = task.get("note") or ""
    if not name:
        return False, "no program name"
    r = subprocess.run(["supervisorctl", "status", name], stdout=subprocess.PIPE, text=True, timeout=8)
    if "RUNNING" in (r.stdout or ""):
        return True, (r.stdout or "").strip()
    subprocess.run(["supervisorctl", "start", name], timeout=8)
    time.sleep(1)
    r2 = subprocess.run(["supervisorctl", "status", name], stdout=subprocess.PIPE, text=True, timeout=8)
    return (("RUNNING" in (r2.stdout or "")), (r2.stdout or r.stdout).strip())


def h_ensure_gpu_watchdog(task):
    name = "nox-gpu-watchdog-t865u"
    r = subprocess.run(["supervisorctl", "status", name],
                       stdout=subprocess.PIPE, text=True, timeout=8)
    if "RUNNING" in (r.stdout or ""):
        return True, (r.stdout or "").strip()
    subprocess.run(["supervisorctl", "start", name], timeout=8)
    time.sleep(1)
    r2 = subprocess.run(["supervisorctl", "status", name],
                        stdout=subprocess.PIPE, text=True, timeout=8)
    ok = "RUNNING" in (r2.stdout or "")
    return (True if ok else "wait"), (r2.stdout or r.stdout).strip()



def h_exec_plan(task):
    """Run an allowlisted plan script. Exit 2 => wait; 0 => done. Never touches chat or gpu watchdog."""
    params = task.get("params") or {}
    script = str(params.get("script") or "").strip()
    allow_tag = ("t866u", "t867u", "t868u", "t877u", "t878u", "t879u", "t880c", "t882u", "t883u", "t884u", "t885u", "t886u", "t887u", "t888u", "t890u", "t892u", "t893u", "t898u", "t899u")
    if not script.startswith("/root/nox/scripts/") or not script.endswith((".sh", ".py")):
        return False, "script not under /root/nox/scripts"
    if not any(t in script for t in allow_tag):
        return False, "script not allowlisted for exec_plan"
    banned = ("chat-8081", "start_chat_8081", "gpu-watchdog", "train_worm_t811u")
    if any(b in script for b in banned):
        return False, "refusing banned script"
    if not Path(script).is_file():
        return "wait", f"script missing: {script}"
    timeout = int(task.get("timeout_sec") or 3600)
    log(f"exec_plan {script} timeout={timeout}s assigned={task.get('assigned_to')}")
    env = os.environ.copy()
    env["TZ"] = "Europe/Moscow"
    try:
        if script.endswith(".sh"):
            cmd = ["/bin/bash", script]
        else:
            cmd = [script]
            extra = params.get("args")
            if isinstance(extra, (list, tuple)):
                cmd.extend(str(a) for a in extra)
            elif params.get("job"):
                cmd.extend(["--job", str(params.get("job"))])
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired as e:
        tail = (e.stdout or "") if isinstance(getattr(e, "stdout", None), str) else ""
        return "wait", f"timeout {timeout}s {tail[-400:]}"
    tail = (r.stdout or "")[-2000:]
    if r.returncode == 0:
        return True, {"rc": 0, "tail": tail[-800:]}
    if r.returncode == 2:
        return "wait", tail[-500:]
    return False, {"rc": r.returncode, "tail": tail[-500:]}


def h_track(task):
    return "wait", "Continuous role exists; no verified completed work is claimed"


def h_owner_order(task):
    """Execute a pending owner order (already paused by scheduler). Then mark done so scheduler resumes."""
    params = task.get("params") or {}
    kind = params.get("kind") or task.get("note") or "generic"
    # dummy test: no side effects
    if "DUMMY" in str(params) or "DUMMY" in str(task.get("title") or "") or kind == "dummy":
        time.sleep(0.2)
        OWNER_DONE.parent.mkdir(parents=True, exist_ok=True)
        OWNER_DONE.write_text(now_msk() + " dummy executed\n")
        return True, {"executed": "dummy", "at": now_msk()}
    # default: record and let architect/dispatcher pick up the new OWNER_* file
    OWNER_DONE.parent.mkdir(parents=True, exist_ok=True)
    OWNER_DONE.write_text(now_msk() + " accepted " + redact(str(params)[:400]) + "\n")
    return True, {"accepted": True, "params": "see events"}


HANDLERS = {
    "wait_q4": h_wait_q4, "verify_q4": h_verify_q4, "delete_q8": h_delete_q8,
    "identity": h_identity, "hot_swap": h_hot_swap, "write_live": h_write_live,
    "start_qlora": h_start_qlora, "holdout_gate": h_holdout_gate,
    "merge_gated": h_merge_gated, "new_gguf": h_new_gguf,
    "ensure_downloads": h_ensure_downloads, "ensure_scheduler": h_ensure_scheduler,
    "ensure_offload": h_ensure_offload, "ensure_program": h_ensure_program,
    "ensure_gpu_watchdog": h_ensure_gpu_watchdog,
    "track": h_track, "owner_order": h_owner_order, "exec_plan": h_exec_plan,
    "owner_component_validate": owner_mentor.handle_component_validation,
    "owner_component": run_component_task,
}


def deps_ok(st, task) -> bool:
    for d in task.get("deps") or []:
        dep = st["tasks"].get(d)
        if not dep or dep.get("status") != "done":
            return False
    return True


def acquire_locks(task) -> bool:
    held = []
    try:
        for name in task.get("locks") or []:
            lk = LOCKS.get(name)
            if lk is None:
                continue
            if not lk.acquire(blocking=False):
                for h in held:
                    h.release()
                return False
            held.append(lk)
        task["_held_locks"] = held
        return True
    except Exception:
        for h in held:
            try:
                h.release()
            except Exception:
                pass
        return False


def release_locks(task):
    for h in task.pop("_held_locks", []) or []:
        try:
            h.release()
        except Exception:
            pass


def pick_ready(st, busy_ids, prefer_lane: Optional[str] = None) -> Optional[dict]:
    ready = []
    now = time.time()
    for t in st["tasks"].values():
        if t.get("id") in busy_ids or t.get("status") not in ("pending", "wait", "retry"):
            continue
        if not _nox_owner_task_admitted(t) or not deps_ok(st, t):
            continue
        try:
            if float(t.get("next_try") or 0) > now:
                continue
        except (TypeError, ValueError):
            continue
        ready.append(t)
    def key(t):
        return owner_mentor.fair_queue_key(t, PRIO, now, prefer_lane)
    return min(ready, key=key) if ready else None


def owner_claim_ready(st, busy, worker_name, prefer_lane=None):
    with _qlock:
        owner_mentor.require_dispatcher_writer(globals())
        if owner_mentor.stop_active():
            return None
        ingest_architect_patch(st)
        ingest_owner_orders(st)
        excluded = set(busy)
        while True:
            task = pick_ready(st, excluded, prefer_lane)
            if task is None:
                return None
            if acquire_locks(task):
                break
            excluded.add(task["id"])
        busy.add(task["id"])
        task["status"] = "running"
        task["claimed_by"] = worker_name
        task.pop("ready_since_epoch", None)
        task["owner_claim_epoch"] = time.time()
        task["owner_claim"] = {"worker": worker_name, "pid": os.getpid(),
                               "nonce": os.urandom(12).hex(), "at": now_msk(),
                               "start_ticks": owner_mentor.process_start_ticks(os.getpid())}
        save_state(st)
        return task


def _endpoint_tok_s() -> dict:
    out = {}
    for name, port in (("chat_8081", 8081), ("teacher_8084", 8084), ("teacher_8086", 8086)):
        try:
            r = subprocess.run(["curl", "-sf", "--max-time", "1", f"http://127.0.0.1:{port}/metrics"],
                               stdout=subprocess.PIPE, text=True, timeout=2)
            raw = r.stdout or ""
            m = re.search(r"^llamacpp:predicted_tokens_seconds\s+([0-9.eE+-]+)$", raw, re.M)
            out[name] = float(m.group(1)) if m else 0.0
        except Exception:
            out[name] = 0.0
    return out


def write_agents_status():
    toks = _endpoint_tok_s()
    with _wlock:
        workers = []
        for i in range(WORKERS):
            rec = dict(_wstate.get(i) or {})
            rec.setdefault("id", f"nox-agent-{i+1:02d}")
            rec.setdefault("lane_preference", LANE_PREFS[i] if i < len(LANE_PREFS) else "background")
            rec.setdefault("current_task", None)
            rec.setdefault("tasks_done", 0)
            rec.setdefault("status", "idle")
            # per-worker tok/s: share chat rate if this worker is busy, else 0
            rec["tok_s"] = None  # Pool throughput is not per-worker measured throughput.
            workers.append(rec)
    doc = {
        "msk": now_msk(),
        "rule": "t856u",
        "n": WORKERS,
        "work_stealing": True,
        "gated_by": "nox-priority-scheduler (chat > owner_order > ...)",
        "owner_order_priority": True,
        "implementation": f"{WORKERS} existing dispatcher task-runner threads; model slots are separate",
        "per_worker_throughput_measured": False,
        "pool_tok_s": toks,
        "workers": workers,
    }
    atomic_write(AGENT_STATUS, doc)



def ingest_council_plan(st, path):
    """Load plan[] scripts from an OWNER_TASKS council file as exec_plan owner_order tasks."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return 0
    n = 0
    for item in doc.get("plan") or []:
        script = str(item.get("script") or "").strip()
        if not script:
            continue
        tid = item.get("id") or ""
        if not tid:
            continue
        cur = (st.get("tasks") or {}).get(tid) or {}
        if cur.get("status") in ("done", "running"):
            continue
        upsert(st, {
            "id": tid,
            "class": "owner_order",
            "priority": int(item.get("priority") or 0),
            "deps": item.get("deps") or [],
            "handler": "exec_plan",
            "title": item.get("goal") or item.get("title") or tid,
            "status": "pending",
            "lane": "owner_order",
            "locks": item.get("locks") or [],
            "retries": 0,
            "max_retries": int(item.get("max_retries") or 3),
            "timeout_sec": int(item.get("timeout_sec") or 1800),
            "assigned_to": item.get("assigned_to") or "nox-agent-integrator-t859u",
            "params": {"script": script},
            "source": doc.get("id") or "council_plan",
        })
        n += 1
    return n



# NOX_MINI_EXISTING_QUEUE_BIND_V1
def ingest_architect_patch(st):
    import owner_mini_tasks
    return owner_mini_tasks.ingest_existing(globals(), st)


def ingest_owner_orders(st):
    """If scheduler posted a new owner order, enqueue a top-priority task."""
    if not OWNER_ACTIVE.exists():
        return
    try:
        doc = json.loads(OWNER_ACTIVE.read_text())
    except Exception:
        return
    if doc.get("cleared"):
        return
    oid = "owner." + hashlib.sha1(json.dumps(doc.get("orders") or doc, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
    if oid in st["tasks"] and st["tasks"][oid].get("status") in ("done", "running"):
        return
    is_dummy = any("DUMMY" in str(o.get("name") or "") for o in (doc.get("orders") or []))
    upsert(st, {
        "id": oid, "class": "owner_order", "priority": 0, "deps": [],
        "handler": "owner_order", "title": "Owner order " + (",".join(o.get("name","") for o in (doc.get("orders") or [])) or "inbox"),
        "status": "pending", "lane": "owner_order", "locks": [],
        "retries": 0, "max_retries": 1, "timeout_sec": 30,
        "params": {"kind": "dummy" if is_dummy else "owner", "orders": doc.get("orders")},
        "source": "t857u",
    })
    for o in doc.get("orders") or []:
        if o.get("kind") == "council_file" and o.get("path"):
            ingest_council_plan(st, o["path"])


def run_one(st, task):
    tid = task["id"]
    handler = HANDLERS.get(task.get("handler") or "")
    failure = None
    with _qlock:
        task["status"] = "running"
        task["started_at"] = now_msk()
        save_state(st)
    ev("start", id=tid, handler=task.get("handler"), claim=task.get("owner_claim"))
    try:
        ok, info = (False, "unknown handler") if handler is None else handler(task)
        with _qlock:
            if ok is True:
                task["status"] = "done"
                task["finished_at"] = now_msk()
                task["result"] = owner_mentor.clean(info)
            elif ok == "wait":
                task["status"] = "pending"
                task["note"] = owner_mentor.redact(info)[:500]
                task["next_try"] = time.time() + 30
            else:
                task["retries"] = int(task.get("retries") or 0) + 1
                task["result"] = owner_mentor.clean(info)
                task["note"] = owner_mentor.redact(info)[:500]
                task["status"] = "blocked"
                task["next_try"] = time.time() + 30
                failure = info
        if ok is True:
            learn(True, tid, task.get("title") or tid, info, task=task)
        elif ok != "wait":
            learn(False, tid, task.get("title") or tid, info, fix="await verified repair", task=task)
    except Exception as exc:
        with _qlock:
            task["status"] = "blocked"
            task["retries"] = int(task.get("retries") or 0) + 1
            task["next_try"] = time.time() + 30
            task["note"] = owner_mentor.redact(type(exc).__name__ + ": " + str(exc))[:500]
            failure = task["note"]
        learn(False, tid, "exception " + tid, failure, fix="await verified repair", task=task)
        log("ERR " + str(tid) + ": " + str(task["note"]))
    finally:
        release_locks(task)
        if failure is not None:
            # Consultation holds neither queue nor GPU resource locks.
            try:
                resolution_task = dict(task)
                owner_mentor.on_failure(resolution_task, failure)
                with _qlock:
                    for key in ("status", "next_try", "mentor", "mentor_incident"):
                        if key in resolution_task:
                            task[key] = resolution_task[key]
            except Exception as exc:
                with _qlock:
                    task["status"] = "blocked"
                    task["mentor"] = {"state": "BLOCKED_MENTOR_JOURNAL", "error": type(exc).__name__}
        with _qlock:
            ev("end", id=tid, status=task.get("status"), claim=task.get("owner_claim"), note=owner_mentor.redact(task.get("note") or "")[:200])
            save_state(st)


def write_status(st):
    with _qlock:
        st = {"tasks": {tid: dict(task) for tid, task in st["tasks"].items()}}
    counts = {}
    items = []
    for t in st["tasks"].values():
        s = t.get("status") or "?"
        counts[s] = counts.get(s, 0) + 1
        items.append({"id": t.get("id"), "class": t.get("class"), "status": s,
                      "title": t.get("title"), "note": (t.get("note") or "")[:200],
                      "deps": t.get("deps") or [],
                      "retry_count": t.get("retries", 0), "retry_limit": t.get("max_retries"),
                      "next_try": t.get("next_try"),
                      "claim_pid": (t.get("owner_claim") or {}).get("pid"),
                      "claim_start_ticks": (t.get("owner_claim") or {}).get("start_ticks"),
                      "ready_since_epoch": t.get("ready_since_epoch")})
    items.sort(key=lambda x: (PRIO.get(x.get("class") or "", 9), x.get("id") or ""))
    gpus = vram()
    downloads = "unknown"
    try:
        r = subprocess.run(["supervisorctl", "status", "nox-downloads-t802u"],
                           stdout=subprocess.PIPE, text=True, timeout=5)
        downloads = (r.stdout or "").strip()
    except Exception:
        pass
    live = None
    if LIVE.exists():
        try:
            live = json.loads(LIVE.read_text())
        except Exception:
            live = {"path": str(LIVE)}
    ident = None
    if IDJSON.exists():
        try:
            d = json.loads(IDJSON.read_text())
            ident = {"pass": d.get("identity_pass"), "ok": d.get("identity_ok"), "ts": d.get("ts_msk")}
        except Exception:
            pass
    swap = SWAP_DONE.read_text().strip() if SWAP_DONE.exists() else None
    q4sz = Q4.stat().st_size if Q4.exists() else 0
    doc = {
        "msk": now_msk(),
        "dispatcher": "nox-dispatcher-t855u",
        "observed_at": time.time(),
        "pid": os.getpid(),
        "start_ticks": owner_mentor.process_start_ticks(os.getpid()),
        "running": True,
        "counts": counts,
        "done": int(counts.get("done") or 0),
        "pending": int(counts.get("pending") or 0) + int(counts.get("wait") or 0) + int(counts.get("retry") or 0),
        "running_count": int(counts.get("running") or 0),
        "failed": int(counts.get("failed") or 0),
        "n_tasks": len(st["tasks"]),
        "pipeline": {
            "q4_bytes": q4sz, "q8_present": Q8.exists(),
            "identity": ident, "swap": swap, "live": (LIVE.exists()),
            "public_chat": PUBLIC,
        },
        "new_model_live": live,
        "downloads": downloads,
        "disk_free_gb": round(disk_free_gb(), 2),
        "vram": gpus,
        "owner_order_active": OWNER_ACTIVE.exists(),
        "owned_by_nox": [
            "nox-dispatcher-t855u", "nox-priority-scheduler", "nox-downloads-t802u",
            "nox-offload-t850u", "nox-distill-worm-t811u", "nox-self-improve-t846u",
            "nox-teacher-serve-t811u", "nox-vram-guard-t829u", "nox-agent-tuner-t858u",
            "nox-agent-integrator-t859u", "nox-agent-architect-t859u",
            "identity/swap path (robust OOM)", "QLoRA start after safe conditions",
        ],
        "tasks": items,
    }
    try:
        with _wlock:
            busy_n = sum(1 for rec in _wstate.values() if rec.get("status") == "busy" or rec.get("current_task"))
            idle_n = max(0, WORKERS - busy_n)
        ready_n = 0
        for tsk in st.get("tasks", {}).values():
            if tsk.get("status") in ("pending", "wait", "retry") and deps_ok(st, tsk):
                ready_n += 1
        doc["agents_busy"] = busy_n
        doc["agents_idle"] = idle_n
        doc["ready_pending"] = ready_n
        # aliases requested by owner/control
        doc["running"] = True
        doc["running_tasks"] = doc["running_count"]
    except Exception as e:
        doc["agents_busy"] = doc.get("agents_busy", 0)
        doc["status_extra_error"] = type(e).__name__
    atomic_write(STATUS, doc)
    # also keep the short status used by older tools
    try:
        short = {
            "msk": doc["msk"],
            "done": doc.get("done"),
            "pending": doc.get("pending"),
            "running": doc.get("running_count"),
            "failed": doc.get("failed"),
            "agents_busy": doc.get("agents_busy"),
            "ready_pending": doc.get("ready_pending"),
            "n_tasks": doc.get("n_tasks"),
        }
        atomic_write(ROOT / "state" / "dispatcher_status.json", short)
    except Exception:
        pass



def ensure_watchdog_task(st: dict) -> None:
    # Supervisor I/O happens outside the task claim lock.
    current = owner_mentor.service_state("nox-gpu-watchdog-t865u")
    with _qlock:
        tid = "ensure.gpu_watchdog"
        task = st.setdefault("tasks", {}).get(tid)
        if not task:
            st["tasks"][tid] = {"id": tid, "class": "watchdog", "priority": 0,
                "deps": [], "handler": "ensure_gpu_watchdog", "title": "Verify GPU watchdog",
                "status": "pending", "locks": [], "retries": 0, "max_retries": 3}
        elif current["state"] != "RUNNING" and task.get("status") == "done":
            task["status"] = "pending"


def main():
    DSTATE.mkdir(parents=True, exist_ok=True)
    owner_mentor.require_dispatcher_writer(globals())
    DISTILL.parent.mkdir(parents=True, exist_ok=True)
    log("dispatcher start t855u work-stealing + owner_order + robust identity")
    st = load_state()
    for t in st.get("tasks", {}).values():
        if t.get("status") == "running":
            t["status"] = "blocked"
            t["note"] = "HOLD: previous in-flight job requires child/process reconciliation before replay"
        t.pop("_held_locks", None)
    seed_if_needed(st)
    ensure_watchdog_task(st)
    save_state(st)
    write_status(st)
    write_agents_status()
    busy = set()
    busy_lock = threading.Lock()

    def worker_loop(wid: int):
        name = f"nox-agent-{wid+1:02d}"
        prefer = LANE_PREFS[wid] if wid < len(LANE_PREFS) else "background"
        while True:
            try:
                task = owner_claim_ready(st, busy, name, prefer)
                if not task:
                    with _wlock:
                        _wstate[wid] = {"id": name, "lane_preference": prefer, "current_task": None,
                                        "tasks_done": _wstate[wid].get("tasks_done", 0),
                                        "tok_s": 0.0, "status": "idle"}
                    time.sleep(0.4)
                    continue
                with _wlock:
                    _wstate[wid] = {"id": name, "lane_preference": prefer,
                                    "current_task": {"id": task.get("id"), "title": task.get("title"),
                                                     "class": task.get("class"), "handler": task.get("handler")},
                                    "tasks_done": _wstate[wid].get("tasks_done", 0),
                                    "tok_s": 0.0, "status": "busy", "started_at": now_msk()}
                try:
                    run_one(st, task)
                    with _wlock:
                        if task.get("status") == "done":
                            _wstate[wid]["tasks_done"] = int(_wstate[wid].get("tasks_done") or 0) + 1
                finally:
                    with _qlock:
                        busy.discard(task["id"])
                    with _wlock:
                        _wstate[wid]["current_task"] = None
                        _wstate[wid]["status"] = "idle"
                        _wstate[wid]["tok_s"] = 0.0
                    write_status(st)
                    write_agents_status()
            except Exception as e:
                log(f"{name} {e}")
                time.sleep(1)

    # also a ticker that reconciles and writes status even if idle
    def ticker():
        while True:
            try:
                ensure_watchdog_task(st)
                with _qlock:
                    reconcile(st)
                    ingest_architect_patch(st)
                    ingest_owner_orders(st)
                    save_state(st)
                write_status(st)
                write_agents_status()
            except Exception as e:
                log(f"ticker {e}")
            time.sleep(5)

    threading.Thread(target=ticker, name="ticker", daemon=True).start()
    with ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="steal") as ex:
        futs = [ex.submit(worker_loop, i) for i in range(WORKERS)]
        for f in as_completed(futs):
            f.result()


# NOX_OWNER_MEDIA_BIND_V1
import owner_media_runtime
owner_media_runtime.bind_dispatcher(globals())

# NOX_OWNER_TASK_PLANS_BIND_V1
import owner_task_plans
owner_task_plans.bind_dispatcher(globals())

# NOX_OWNER_S03_DISPATCHER_BIND_V1
import owner_s03_gateway
LOCKS['shared_memory_index'] = threading.Lock()
owner_s03_gateway.bind_dispatcher(globals())

# NOX_OWNER_TASK_LIFECYCLE_BIND_V1
import owner_task_lifecycle
owner_task_lifecycle.bind_dispatcher(globals(), {'owner_mentor': 'eafaae8c14abe84fd3cfdfbc60b8ac43d2426b0b29f31e11334c064bc373be5f', 'owner_event_outbox': 'e15d458f9d1f03b23fcbf0267206621769ff92f2bfe00d3baf79217e2ab74a02', 'owner_media_runtime': 'ca8ce2466d0ee4321e17bbf2dc26a6f6396bafb93f3df361a1b35a7e8e3347e5', 'owner_task_plans': '9500a72135941ecf801854c040041df72df5c9a1b1da9ee4337631600d8ba7d4', 'owner_senior_gateway': '1fd1556009ce62fa806bdee0a9a34577d276344e728fe9d94b33f44eb151346e', 'owner_s03_gateway': 'cb7f373cf2d3c4f01d47ed4ef0c48b0a89af7a05eb92a06530752c40453fdf20'})

if __name__ == "__main__":
    main()

