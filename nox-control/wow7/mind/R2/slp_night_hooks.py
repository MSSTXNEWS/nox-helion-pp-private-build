"""R2/slp_night_hooks.py: боевые Hooks для SLP с едиными воротами. Подключение: NOX_SLP_HOOKS=slp_night_hooks:Hooks python3 sleep_cycle.py run ...
Env: NOX_STATE, NOX_BENCH_CAND_CMD (команда с {gguf} {out}: поднять временное ядро на кандидате, mind_bench run --split all, POST /v1/core/eval/purge),
     NOX_BENCH_BASELINE, NOX_SIG_DIR, NOX_GATE_LEDGER. Без NOX_BENCH_CAND_CMD ночь НЕ принимается (нет бенча = рост не доказан)."""
import glob
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
for _d in (_HERE, os.path.join(_ROOT, "SLP"), os.path.join(_ROOT, "MIND", "M4_BENCH")):
    if _d not in sys.path:
        sys.path.append(_d)
import sleep_cycle as SC
import mind_bench as MB
import slp_hooks as H
import anti_sycophancy as AS

STATE = os.environ.get("NOX_STATE", "/root/nox/state")
SD = os.path.join(STATE, "selfdev")


def _train_paths(day):
    ps = [os.path.join(STATE, "feedback.jsonl")]
    ps += sorted(glob.glob(os.path.join(STATE, "sleep", day, "data", "kto_train.jsonl")))
    return [p for p in ps if os.path.exists(p)]


def _frozen():
    try:
        return MB.load_suite(None, None, "all")["tasks"]
    except (OSError, ValueError):
        return None


def _no_bench(cfg, gguf):
    raise RuntimeError("NOX_BENCH_CAND_CMD не задан: бенч кандидата невозможен")


def _syc_inputs(cfg, fi, rep, base_rep, day):
    """disagree_rate по журналу+трассе ядра, проба «неправый Создатель» из fidelity, honesty из MIND-BENCH (кандидат vs принятый чемпион)."""
    import time
    return AS.collect_inputs(STATE, os.environ.get("NOX_TRACE_DIR", os.path.join(STATE, "traces")), time.time(),
                             fid_cand=(fi.get("cand") or {}), fid_base=(fi.get("base") or {}), bench_cand=rep, bench_base=base_rep)


class Hooks(SC.Hooks):
    extra_gate = staticmethod(H.make_extra_gate(
        H.bench_via_cmd(os.environ["NOX_BENCH_CAND_CMD"]) if os.environ.get("NOX_BENCH_CAND_CMD") else _no_bench,
        os.environ.get("NOX_BENCH_BASELINE", os.path.join(SD, "bench_baseline.json")),
        train_paths=_train_paths, frozen_tasks=_frozen,
        sig_dir=os.environ.get("NOX_SIG_DIR", os.path.join(STATE, "signatures")),
        ledger_path=os.environ.get("NOX_GATE_LEDGER", os.path.join(SD, "gate_ledger.jsonl")),
        last_path=os.path.join(SD, "last_gate.json"), syc_inputs=_syc_inputs))
