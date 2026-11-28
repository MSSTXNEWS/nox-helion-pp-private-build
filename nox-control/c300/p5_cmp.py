import json, sys
b = json.load(open(sys.argv[1]))["res"]; n = json.load(open(sys.argv[2]))["res"]
def g(r, s, k): return (r.get(s) or {}).get(k)
rows = [("c1_cold", "ttft_p50"), ("c1_cold", "ttft_p95"), ("c3_cold", "ttft_p95"), ("c1_bg3_cold", "ttft_p50"), ("c1_bg3_cold", "ttft_p95"), ("c1_bg3_warm", "ttft_p95"), ("c1_warm", "dec_med"), ("c1_bg3_warm", "dec_med"), ("c3_cold", "agg_tok_s")]
gain = {}
for s, k in rows:
    x, y = g(b, s, k), g(n, s, k)
    if x is None or y is None: print("CMP", s, k, x, y); continue
    ch = (y - x) / x * 100 if x else 0; gain[(s, k)] = ch; print("CMP %s %s base=%s new=%s %+.0f%%" % (s, k, x, y, ch))
q = n["quality"]; qb = b["quality"]
qok = q["distinct"] >= 11 and q["empty"] == 0 and q["checks"]["arith403"] and q["checks"]["canberra"] and q["checks"]["code"] and 0.6 * qb["avg_len"] <= q["avg_len"] <= 1.5 * qb["avg_len"]
errs = sum((n.get(s) or {}).get("err", 0) for s in n if s != "label" and s != "quality")
print("QUALITY", q, "ok", qok, "errs", errs)
better = gain.get(("c1_bg3_cold", "ttft_p95"), 0) <= -10 or gain.get(("c1_bg3_warm", "dec_med"), 0) >= 10 or gain.get(("c1_warm", "dec_med"), 0) >= 10
worse = any(gain.get(k, 0) >= 10 for k in [("c1_bg3_cold", "ttft_p95"), ("c1_bg3_cold", "ttft_p50")]) or any(gain.get(k, 0) <= -10 for k in [("c1_warm", "dec_med"), ("c1_bg3_warm", "dec_med")])
print("VERDICT", "KEEP" if (better and not worse and qok and errs == 0) else "REVERT", "better", better, "worse", worse)
