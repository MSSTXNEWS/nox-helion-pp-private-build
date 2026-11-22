#!/usr/bin/env python3
"""make_matrix.py: строит matrix_v7.json из SPD/matrix.json для этапа S1_03.
Порядок рычагов по критическому пути (один за раз, --accumulate): потоки L01, ub/op-offload L02 L03, cache-reuse L08, cache-ram L09, NUMA L10, no-repack L12, ngram L07,
затем MTP L05 L06 - ТОЛЬКО если --mtp (решение OPT-02). Всегда выкидываются: X01 (KV-квант: запрет), L04 и L11 (moe-cache/ngl - их крутит свип gpu_tier; вернуть --include-sweep).
--base-from FILE: base = флаги из файла (glm.args/GLM_ARGS.best) без -m/--host/--port; рычаги, не меняющие base, удаляются.
Использование: make_matrix.py --src SPD/matrix.json --out matrix_v7.json [--base-from F] [--mtp] [--include-sweep]"""
import argparse
import json
import shlex
import sys

ORDER = ["L01_threads_phys", "L02_ub1024_opoffload", "L03_ub2048_opoffload", "L08_cache_reuse", "L09_cache_ram", "L10_numa_distribute", "L12_no_repack", "L07_ngram"]
MTP = ["L05_mtp_n2", "L06_mtp_n3"]
SWEEP = ["L04_moe_cache_4g", "L11_ngl_up"]
SKIP_ALWAYS = ["X01_kv_q8_QUALITY_ONLY"]
DROP_BASE = ("-m", "--model", "--host", "--port")


def parse_flags(text):
    toks = shlex.split(text)
    out, i = [], 0
    while i < len(toks):
        t = toks[i]
        if t in DROP_BASE:
            i += 2
            continue
        out.append(t)
        i += 1
    return out


def as_map(args):
    m, i = {}, 0
    while i < len(args):
        t = args[i]
        if t.startswith("-") and i + 1 < len(args) and not (args[i + 1].startswith("-") and not args[i + 1].lstrip("-").replace(".", "").isdigit()):
            m[t] = args[i + 1]; i += 2
        else:
            m[t] = None; i += 1
    return m


def noop(lever, base):
    """Рычаг ничего не меняет, если все set уже в base с тем же значением и всё из drop уже отсутствует."""
    bm = as_map(base)
    same = all(k in bm and (v == "" and bm[k] is None or str(bm[k]) == str(v)) for k, v in lever.get("set", {}).items())
    gone = all(d not in bm for d in lever.get("drop", []))
    return same and gone and not lever.get("env")


def build(src, base_text=None, mtp=False, include_sweep=False):
    m = json.loads(json.dumps(src))
    if base_text and base_text.strip():
        m["base"] = parse_flags(base_text)
    by = {lv["id"]: lv for lv in m["levers"]}
    ids = list(ORDER) + (SWEEP if include_sweep else []) + (MTP if mtp else [])
    levers, dropped = [], []
    for i in ids:
        lv = by.get(i)
        if lv is None:
            continue
        if noop(lv, m["base"]):
            dropped.append({"id": i, "why": "уже в base"})
            continue
        levers.append(lv)
    for i in by:
        if i not in ids:
            dropped.append({"id": i, "why": "запрет" if i in SKIP_ALWAYS else ("свип gpu_tier" if i in SWEEP else "MTP: нет решения OPT-02" if i in MTP else "не в порядке v7")})
    m["levers"] = levers
    m["_doc"] = "matrix_v7 (S1_03): порядок критического пути; " + m.get("_doc", "")
    m["_dropped"] = dropped
    return m


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", required=True); ap.add_argument("--out", required=True); ap.add_argument("--base-from", default="")
    ap.add_argument("--mtp", action="store_true"); ap.add_argument("--include-sweep", action="store_true")
    a = ap.parse_args(argv)
    src = json.load(open(a.src, encoding="utf-8"))
    base = open(a.base_from, encoding="utf-8").read() if a.base_from else None
    m = build(src, base, a.mtp, a.include_sweep)
    json.dump(m, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("рычагов: %d (%s); убрано: %d" % (len(m["levers"]), ",".join(l["id"] for l in m["levers"]), len(m["_dropped"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
