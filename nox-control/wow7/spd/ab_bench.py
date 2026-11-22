#!/usr/bin/env python3
"""SPD-02 ab_bench: A/B-харнесс llama-server для GLM-5.3 на S1. Один рычаг за раз.

Поднимает llama-server по matrix.json (base + ровно один рычаг), меряет по стриму /completion:
TTFT, pp (prompt_per_second), tg (predicted_per_second) из timings, кэш-тест (повтор и сдвиг префикса),
качество (сходство greedy-ответа с базовым), проверяет ЗАПРЕТЫ, пишет JSON/CSV и winner.json.
Только stdlib. Не трогает уже работающий сервер: если порт занят — отказ (или --attach для одного замера).

Примеры:
  python3 ab_bench.py --dry-run
  python3 ab_bench.py --bin /root/nox/llama.cpp/build/bin/llama-server --model /root/nox/glm53/GLM-5.3-UD-Q4_K_XL-00001-of-00011.gguf --port 8091 --accumulate
  python3 ab_bench.py --attach http://127.0.0.1:8081 --only base
"""
import argparse
import copy
import csv
import difflib
import http.client
import json
import os
import statistics
import subprocess
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DEF_BIN = "/root/nox/llama.cpp/build/bin/llama-server"
DEF_MODEL = "/root/nox/glm53/GLM-5.3-UD-Q4_K_XL-00001-of-00011.gguf"


# ---------------------------------------------------------------- аргументы
def _is_flag(tok):
    return isinstance(tok, str) and tok.startswith("-") and not _is_number(tok)


def _is_number(tok):
    try:
        float(tok)
        return True
    except (TypeError, ValueError):
        return False


def parse_args_list(args):
    """['-c','16384','--jinja'] -> [('-c','16384'),('--jinja',None)] (порядок сохраняется)."""
    out, i = [], 0
    while i < len(args):
        t = args[i]
        if _is_flag(t) and i + 1 < len(args) and not _is_flag(args[i + 1]):
            out.append((t, args[i + 1]))
            i += 2
        else:
            out.append((t, None))
            i += 1
    return out


def flatten(pairs):
    flat = []
    for k, v in pairs:
        flat.append(k)
        if v is not None:
            flat.append(v)
    return flat


def apply_lever(base_args, lever):
    """Возвращает новый список аргументов: base + set (замена/добавление) - drop. Исходный не меняется."""
    pairs = parse_args_list(base_args)
    for k in lever.get("drop", []):
        pairs = [p for p in pairs if p[0] != k]
    for k, v in lever.get("set", {}).items():
        for i, p in enumerate(pairs):
            if p[0] == k:
                pairs[i] = (k, v)
                break
        else:
            pairs.append((k, v if v != "" else None))
    return flatten(pairs)


def get_flag(args, name, default=None):
    for k, v in parse_args_list(args):
        if k == name:
            return v
    return default


# ---------------------------------------------------------------- запреты
def check_bans(args, bans, allow_kv_quant=False):
    """Список нарушений ЗАПРЕТОВ для набора аргументов (пустой = можно)."""
    bad = []
    pairs = parse_args_list(args)
    names = [k for k, _ in pairs]
    for f in bans.get("flags", []):
        if f.split("=")[0] in names:
            bad.append("запрещён флаг %s" % f)
    if not allow_kv_quant:
        ok_vals = set(bans.get("kv_quant_allowed_values", ["f16"]))
        for k, v in pairs:
            if k in bans.get("kv_quant_flags", []) and v not in ok_vals:
                bad.append("KV-квантование %s %s без A/B качества" % (k, v))
    for k, v in pairs:
        if k in ("-c", "--ctx-size"):
            try:
                if int(v) < int(bans.get("min_ctx", 0)):
                    bad.append("контекст %s < %s" % (v, bans["min_ctx"]))
            except (TypeError, ValueError):
                bad.append("непонятный контекст %r" % (v,))
    return bad


# ---------------------------------------------------------------- HTTP-замеры
def http_json(url, payload=None, timeout=30):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode("utf-8", "replace")
    return json.loads(body) if body.strip() else {}


def healthy(base_url, timeout=2):
    try:
        with urllib.request.urlopen(base_url + "/health", timeout=timeout) as r:
            return r.status == 200 and b"ok" in r.read().lower()
    except Exception:
        return False


def stream_completion(base_url, prompt, n_predict, cache_prompt=False, temperature=0.0, timeout=900):
    """Стрим /completion. Возвращает dict: ttft_s, total_s, text, timings (из последнего чанка)."""
    u = urllib.parse.urlparse(base_url)
    conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=timeout)
    body = json.dumps({"prompt": prompt, "n_predict": n_predict, "stream": True,
                       "cache_prompt": cache_prompt, "temperature": temperature,
                       "top_k": 1 if temperature == 0 else 40})
    t0 = time.time()
    conn.request("POST", "/completion", body, {"Content-Type": "application/json"})
    resp = conn.getresponse()
    if resp.status != 200:
        raise RuntimeError("HTTP %s: %s" % (resp.status, resp.read()[:200]))
    ttft, text, timings = None, "", {}
    while True:
        line = resp.readline()
        if not line:
            break
        line = line.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            d = json.loads(payload)
        except ValueError:
            continue
        c = d.get("content") or ""
        if c and ttft is None:
            ttft = time.time() - t0
        text += c
        if d.get("timings"):
            timings = d["timings"]
        if d.get("stop"):
            break
    conn.close()
    total = time.time() - t0
    if ttft is None:
        ttft = total
    return {"ttft_s": ttft, "total_s": total, "text": text, "timings": timings}


def _med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def measure(base_url, bench, quality):
    """Полный набор замеров для уже поднятого сервера."""
    to = bench.get("timeout_s", 900)
    short = bench["short_prompt"]
    long_p = ("Сервер обрабатывает запросы пользователей и пишет журнал событий. " * int(bench["long_repeat"])) + "Кратко:"
    stream_completion(base_url, "Привет", 4, timeout=to)  # прогрев (страницы mmap, CUDA-графы)
    ttfts, tgs, pps, long_ttfts = [], [], [], []
    for _ in range(int(bench["repeats"])):
        r = stream_completion(base_url, short, int(bench["short_n"]), timeout=to)
        ttfts.append(r["ttft_s"])
        tgs.append(r["timings"].get("predicted_per_second"))
        r2 = stream_completion(base_url, long_p, int(bench["long_n"]), timeout=to)
        pps.append(r2["timings"].get("prompt_per_second"))
        long_ttfts.append(r2["ttft_s"])
    # кэш-тест: повтор того же префикса, затем «сдвиг» (вырезан блок из середины)
    n_cache = int(bench.get("cache_n", 8))
    blk = lambda i: ("Блок %d. " % i) + ("Факт о системе номер %d сохранён в памяти. " % i) * 25
    A, B, C = blk(1), blk(2), blk(3)
    r_first = stream_completion(base_url, A + B + C + " Итог:", n_cache, cache_prompt=True, timeout=to)
    r_rep = stream_completion(base_url, A + B + C + " Итог:", n_cache, cache_prompt=True, timeout=to)
    r_shift = stream_completion(base_url, A + C + " Итог:", n_cache, cache_prompt=True, timeout=to)
    t1, t2, t3 = r_first["timings"], r_rep["timings"], r_shift["timings"]
    q = stream_completion(base_url, quality["prompt"], int(quality["n_predict"]), timeout=to)
    return {
        "ttft_short_s": _med(ttfts), "tg": _med(tgs), "pp": _med(pps), "ttft_long_s": _med(long_ttfts),
        "cache": {
            "first_prompt_n": t1.get("prompt_n"), "repeat_prompt_n": t2.get("prompt_n"),
            "repeat_cache_n": t2.get("cache_n"), "repeat_ttft_s": r_rep["ttft_s"], "first_ttft_s": r_first["ttft_s"],
            "shift_prompt_n": t3.get("prompt_n"), "shift_cache_n": t3.get("cache_n"),
        },
        "quality_text": q["text"],
    }


# ---------------------------------------------------------------- решение
def similarity(a, b):
    return difflib.SequenceMatcher(None, a or "", b or "").ratio()


def score(m, base_m, dec):
    """Геометрическая смесь относительных приростов: tg, pp, 1/ttft. >1 = лучше базы."""
    def ratio(x, y, inv=False):
        if not x or not y:
            return 1.0
        return (y / x) if inv else (x / y)
    return (ratio(m["tg"], base_m["tg"]) ** dec["w_tg"]
            * ratio(m["pp"], base_m["pp"]) ** dec["w_pp"]
            * ratio(m["ttft_short_s"], base_m["ttft_short_s"], inv=True) ** dec["w_ttft"])


def verdict(m, base_m, dec, quality_cfg):
    sim = similarity(m.get("quality_text"), base_m.get("quality_text"))
    s = score(m, base_m, dec)
    reasons = []
    if sim < quality_cfg["min_similarity"]:
        reasons.append("качество: сходство %.2f < %.2f" % (sim, quality_cfg["min_similarity"]))
    if base_m["tg"] and m["tg"] and m["tg"] < base_m["tg"] * (1 - dec["max_tg_regress"]):
        reasons.append("tg просел на >%d%%" % int(dec["max_tg_regress"] * 100))
    if s < 1 + dec["min_gain"]:
        reasons.append("прирост %.1f%% < порога %.0f%%" % ((s - 1) * 100, dec["min_gain"] * 100))
    return {"score": s, "similarity": sim, "accepted": not reasons, "reasons": reasons}


# ---------------------------------------------------------------- сервер
def help_text(binpath):
    try:
        p = subprocess.run([binpath, "--help"], capture_output=True, text=True, timeout=60)
        return (p.stdout or "") + (p.stderr or "")
    except Exception:
        return ""


class Server:
    def __init__(self, binpath, model, port, args, env, log_path):
        self.cmd = [binpath, "-m", model, "--host", "127.0.0.1", "--port", str(port)] + list(args)
        self.env = dict(os.environ)
        self.env.update(env or {})
        self.log_path = log_path
        self.proc = None
        self.url = "http://127.0.0.1:%d" % port

    def start(self, health_timeout):
        self.log = open(self.log_path, "wb")
        self.proc = subprocess.Popen(self.cmd, env=self.env, stdout=self.log, stderr=subprocess.STDOUT)
        t0 = time.time()
        while time.time() - t0 < health_timeout:
            if self.proc.poll() is not None:
                raise RuntimeError("сервер упал (rc=%s), см. %s" % (self.proc.returncode, self.log_path))
            if healthy(self.url):
                return time.time() - t0
            time.sleep(1.0)
        raise RuntimeError("health-timeout %ss" % health_timeout)

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(30)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(10)
        if getattr(self, "log", None):
            self.log.close()


def run_config(cfg_id, args, env, a, matrix, base_metrics=None):
    """Поднять сервер с args/env, замерить, остановить. Возвращает dict результата."""
    res = {"id": cfg_id, "args": args, "env": env, "ok": False}
    srv = Server(a.bin, a.model, a.port, args, env, os.path.join(a.out, "server_%s.log" % cfg_id))
    try:
        res["load_s"] = round(srv.start(matrix["bench"].get("health_timeout_s", 1500)), 1)
        res["metrics"] = measure(srv.url, matrix["bench"], matrix["quality"])
        res["ok"] = True
    except Exception as e:  # падение конфигурации (OOM и т.п.) — это результат, а не авария харнесса
        res["error"] = str(e)[:300]
    finally:
        srv.stop()
    return res


def other_main_running(model_hint="glm"):
    """ЗАПРЕТ «одна главная модель за раз»: живые процессы llama-server с GLM в командной строке (Linux, /proc)."""
    found = []
    try:
        pids = [p for p in os.listdir("/proc") if p.isdigit()]
    except OSError:
        return found
    for p in pids:
        try:
            with open("/proc/%s/comm" % p) as f:
                if f.read().strip() != "llama-server":
                    continue
            with open("/proc/%s/cmdline" % p, "rb") as f:
                cl = f.read().replace(b"\0", b" ").decode("utf-8", "replace")
        except OSError:
            continue
        if model_hint.lower() in cl.lower():
            found.append("%s %s" % (p, cl[:100]))
    return found


# ---------------------------------------------------------------- основной цикл
def plan(matrix, only=None, accumulate=False, allow_kv_quant=False, help_txt=None, skip_help_check=False):
    """Список шагов без запуска: [{id, args, env, skip}] — для --dry-run и тестов."""
    steps = [{"id": "base", "args": list(matrix["base"]), "env": dict(matrix.get("base_env", {})), "skip": None}]
    for lv in matrix["levers"]:
        if only is not None and lv["id"] not in only:
            continue
        args = apply_lever(matrix["base"], lv)
        env = dict(matrix.get("base_env", {}))
        env.update(lv.get("env", {}))
        skip = None
        bad = check_bans(args, matrix["bans"], allow_kv_quant)
        if bad:
            skip = "ЗАПРЕТ: " + "; ".join(bad)
        elif not skip_help_check and help_txt is not None:
            miss = [r for r in lv.get("requires_help", []) if r not in help_txt]
            if miss:
                skip = "сборка не поддерживает: " + ", ".join(miss)
        steps.append({"id": lv["id"], "args": args, "env": env, "skip": skip, "lever": lv})
    return steps


def write_outputs(out, results, winner):
    with open(os.path.join(out, "results.json"), "w", encoding="utf-8") as f:
        json.dump({"results": results, "winner": winner}, f, ensure_ascii=False, indent=1)
    with open(os.path.join(out, "results.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "status", "load_s", "ttft_short_s", "tg_tok_s", "pp_tok_s", "ttft_long_s",
                    "repeat_cache_n", "repeat_prompt_n", "shift_cache_n", "similarity", "score", "accepted", "note"])
        for r in results:
            m, v = r.get("metrics") or {}, r.get("verdict") or {}
            c = m.get("cache") or {}
            status = "skip" if r.get("skip") else ("ok" if r.get("ok") else "fail")
            w.writerow([r["id"], status, r.get("load_s"), _r(m.get("ttft_short_s")), _r(m.get("tg")), _r(m.get("pp")),
                        _r(m.get("ttft_long_s")), c.get("repeat_cache_n"), c.get("repeat_prompt_n"),
                        c.get("shift_cache_n"), _r(v.get("similarity")), _r(v.get("score")), v.get("accepted"),
                        r.get("skip") or r.get("error") or "; ".join(v.get("reasons", []))])
    with open(os.path.join(out, "winner.json"), "w", encoding="utf-8") as f:
        json.dump(winner, f, ensure_ascii=False, indent=1)


def _r(x, n=3):
    return round(x, n) if isinstance(x, (int, float)) else x


def run(a):
    with open(a.matrix, encoding="utf-8") as f:
        matrix = json.load(f)
    os.makedirs(a.out, exist_ok=True)
    only = (set() if a.only == "base" else set(a.only.split(","))) if a.only else None
    htxt = None if a.dry_run or a.attach else help_text(a.bin)
    steps = plan(matrix, only, a.accumulate, a.allow_kv_quant, htxt, skip_help_check=bool(a.dry_run or a.attach))
    if a.dry_run:
        for s in steps:
            print("%-26s %s" % (s["id"], "SKIP " + s["skip"] if s["skip"] else
                                (" ".join("%s=%s" % kv for kv in s["env"].items()) + " " + " ".join([a.bin, "-m", a.model] + s["args"]))))
        return 0
    dec, qcfg = matrix["decision"], matrix["quality"]
    results = []
    if a.attach:  # один замер уже работающего сервера, без перезапуска
        m = measure(a.attach.rstrip("/"), matrix["bench"], matrix["quality"])
        winner = {"id": "attached", "args": None, "metrics": m, "note": "замер без перезапуска"}
        results.append({"id": "attached", "ok": True, "metrics": m})
        write_outputs(a.out, results, winner)
        print(json.dumps({"tg": m["tg"], "pp": m["pp"], "ttft_s": m["ttft_short_s"]}))
        return 0
    if healthy("http://127.0.0.1:%d" % a.port):
        print("порт %d занят живым сервером — отказ (не трогаю чужой llama-server). Укажи другой --port." % a.port, file=sys.stderr)
        return 3
    others = other_main_running()
    if others:
        print("ЗАПРЕТ: одна главная модель за раз, но уже работает: %s\nОстанови её (start_glm_best.sh потом вернёт победителя) и запусти снова." % others[0], file=sys.stderr)
        return 6
    cur_args, cur_env = list(matrix["base"]), dict(matrix.get("base_env", {}))
    bad = check_bans(cur_args, matrix["bans"], a.allow_kv_quant)
    if bad:
        print("base нарушает запреты: " + "; ".join(bad), file=sys.stderr)
        return 4
    base = run_config("base", cur_args, cur_env, a, matrix)
    results.append(base)
    if not base["ok"]:
        write_outputs(a.out, results, {"id": "base", "error": base.get("error")})
        print("base не поднялся: %s" % base.get("error"), file=sys.stderr)
        return 5
    ref = base["metrics"]
    cur_metrics, winner = ref, {"id": "base", "args": cur_args, "env": cur_env, "metrics": ref}
    for s in steps[1:]:
        if s["skip"]:
            results.append({"id": s["id"], "skip": s["skip"], "args": s["args"]})
            continue
        # accumulate: рычаг накладывается на текущего победителя; иначе — на исходную базу (чистый «один рычаг»)
        lv_args = apply_lever(cur_args if a.accumulate else matrix["base"], s["lever"])
        lv_env = dict(cur_env if a.accumulate else matrix.get("base_env", {}))
        lv_env.update(s["lever"].get("env", {}))
        bad = check_bans(lv_args, matrix["bans"], a.allow_kv_quant)
        if bad:
            results.append({"id": s["id"], "skip": "ЗАПРЕТ: " + "; ".join(bad), "args": lv_args})
            continue
        r = run_config(s["id"], lv_args, lv_env, a, matrix)
        if r["ok"]:
            r["verdict"] = verdict(r["metrics"], cur_metrics if a.accumulate else ref, dec, qcfg)
            if r["verdict"]["accepted"]:
                if a.accumulate:
                    cur_args, cur_env, cur_metrics = lv_args, lv_env, r["metrics"]
                    winner = {"id": s["id"], "args": cur_args, "env": cur_env, "metrics": r["metrics"],
                              "score_vs_prev": r["verdict"]["score"]}
                elif r["verdict"]["score"] > winner.get("score_vs_base", 1.0):
                    winner = {"id": s["id"], "args": lv_args, "env": lv_env, "metrics": r["metrics"],
                              "score_vs_base": r["verdict"]["score"]}
        results.append(r)
    winner["base_metrics"] = ref
    write_outputs(a.out, results, winner)
    print("победитель: %s" % winner["id"])
    print("args: %s" % " ".join(winner.get("args") or []))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--matrix", default=os.path.join(HERE, "matrix.json"))
    ap.add_argument("--bin", default=DEF_BIN)
    ap.add_argument("--model", default=DEF_MODEL)
    ap.add_argument("--port", type=int, default=8091, help="не 8081: основной сервер не трогаем")
    ap.add_argument("--out", default="/root/nox/logs/spd_ab")
    ap.add_argument("--only", default="", help="id рычагов через запятую (base = только базовый замер при --attach)")
    ap.add_argument("--accumulate", action="store_true", help="закреплять принятый рычаг и тестировать следующий поверх него")
    ap.add_argument("--allow-kv-quant", action="store_true", help="разрешить KV-квантование (только для A/B качества)")
    ap.add_argument("--attach", default="", help="URL уже запущенного сервера: один замер без перезапуска")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
