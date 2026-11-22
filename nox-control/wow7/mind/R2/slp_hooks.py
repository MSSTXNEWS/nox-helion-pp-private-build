"""R2/slp_hooks.py: подключение gate_all к ночному циклу SLP (sleep_cycle.Hooks.extra_gate).

    from slp_hooks import make_extra_gate, bench_via_cmd
    class H(SC.Hooks): extra_gate = staticmethod(make_extra_gate(bench_via_cmd("bash /root/nox/scripts/mind/bench_candidate.sh {gguf} {out}"), ...))

Бенч кандидата считается внешней командой (она поднимает временное ядро на кандидате и вызывает mind_bench.py run --split all, затем POST /v1/core/eval/purge) - это
изолирует тяжёлую часть и позволяет тестировать ворота без GPU.
"""
import json
import os
import shlex
import subprocess
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)
import gate_all as G


def bench_via_cmd(template, timeout=7200):
    """template с {gguf} и {out}; команда пишет отчёт MIND-BENCH в {out}. -> callable(cfg, gguf) -> dict."""
    def run(cfg, gguf):
        fd, out = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            cmd = template.format(gguf=shlex.quote(str(gguf)), out=shlex.quote(out))
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
            with open(out, encoding="utf-8") as f:
                return json.load(f)
        finally:
            try:
                os.remove(out)
            except OSError:
                pass
    return run


def _load(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def make_extra_gate(bench_run, baseline_path, train_paths=(), frozen_tasks=None, sig_dir=None, ledger_path=None, meta=None, on_accept_baseline=False, last_path=None, syc_inputs=None):
    """-> callable(cfg, tr, fi, day) для sleep_cycle. baseline_path: отчёт принятого чемпиона (обновляется при принятии)."""
    def extra(cfg, tr, fi, day):
        holder = {}

        def cand():
            holder["rep"] = bench_run(cfg, tr["gguf"])
            return holder["rep"]
        def syc():
            return syc_inputs(cfg, fi, holder.get("rep"), _load(baseline_path), day)
        res = G.run_gate("adapter", "night-" + day, sycophancy=syc if syc_inputs else None, require_sycophancy=bool(syc_inputs), fid_cand=fi["cand"], fid_base=fi.get("base"), bench_cand=cand, bench_base=_load(baseline_path),
                         train_paths=list(train_paths(day) if callable(train_paths) else train_paths), frozen_tasks=frozen_tasks() if callable(frozen_tasks) else frozen_tasks, meta=meta, sig_dir=sig_dir, ledger_path=ledger_path)
        if last_path:
            os.makedirs(os.path.dirname(os.path.abspath(last_path)), exist_ok=True)
            rep = holder.get("rep") or {}
            with open(last_path, "w", encoding="utf-8") as f:
                json.dump(dict(res, bench_overall=rep.get("overall"), bench_holdout=(rep.get("splits") or {}).get("holdout"), bench_report=holder.get("rep")), f, ensure_ascii=False)
        if res["pass"] and on_accept_baseline and holder.get("rep"):
            os.makedirs(os.path.dirname(os.path.abspath(baseline_path)), exist_ok=True)
            with open(baseline_path, "w", encoding="utf-8") as f:
                json.dump(holder["rep"], f, ensure_ascii=False)
        return res
    return extra
