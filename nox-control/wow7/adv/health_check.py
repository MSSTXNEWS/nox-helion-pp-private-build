#!/usr/bin/env python3
"""health_check: ЖИВОЙ опрос каждого провайдера из advisors_live.json с квитанцией.

Для каждого включённого провайдера: (1) ключ в env есть? (нет -> no_key, это не сбой); (2) GET /models (если есть);
(3) один крошечный запрос «pong»; статус ok | no_key | auth_fail | rate_limited | model_missing | net_error | empty. Плюс поиск: SearXNG и Wikipedia.
Выключенные (платные, retired) не опрашиваются - в квитанции skipped с причиной. Ключи в вывод/квитанцию не попадают.
Пробный запрос тратит 1 запрос квоты провайдера (в учёт пула не пишется). --stamp проставляет live_checked/live_ts в реестре.
Использование: health_check.py [--only a,b] [--timeout 30] [--receipt PATH] [--stamp] [--registry PATH]
"""
import argparse
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import advisor_hub as hub  # noqa: E402
ap = hub.ap


def classify(exc):
    code = getattr(exc, "code", 0)
    if code in (401, 403):
        return "auth_fail"
    if code in (402, 429):
        return "rate_limited"
    if code == 404:
        return "model_missing"
    return "net_error"


def check_provider(p, env, timeout, transport=None, models_fn=None):
    rec = {"name": p["name"], "family": p.get("family"), "model": p.get("model", ""), "status_registry": p.get("status")}
    if p.get("status") == "needs_free_confirm":
        has = bool(env.get(p.get("api_key_env", "")))
        rec.update(status="needs_free_confirm" if has else "no_key", key_url=p.get("key_url", ""),
                   reason="ключ есть, но не подтверждено 'без оплаты': добавь имя в NOX_ADV_FREE_CONFIRMED" if has else "нет переменной %s" % p.get("api_key_env"))
        return rec
    if not p.get("enabled", True):
        rec.update(status="skipped", reason=p.get("status") or "disabled")
        return rec
    kenv = p.get("api_key_env", "")
    key = env.get(kenv, "")
    if p["kind"] == "openai" and not key:
        rec.update(status="no_key", reason="нет переменной %s" % kenv, key_url=p.get("key_url", ""))
        return rec
    t0 = time.time()
    model = p.get("model", "")
    ids = None
    try:
        if p["kind"] == "openai":
            try:
                ids = (models_fn or ap.list_models)(p, key, min(timeout, 15))
            except Exception:  # noqa: BLE001  /models есть не у всех; не критично
                ids = None
            if not model:
                if ids is None:
                    rec.update(status="net_error", reason="/models недоступен, модель не задана")
                    return rec
                pick = [i for i in ids if re.search(p.get("model_filter", "."), i)]
                if not pick:
                    rec.update(status="model_missing", reason="по фильтру %s ничего" % p.get("model_filter"), models_total=len(ids))
                    return rec
                model = pick[0]
            elif ids is not None and model not in ids and ("models/" + model) not in ids:
                rec["warn"] = "модель %s не в /models (из %d)" % (model, len(ids))
        pp = dict(p, model=model, max_tokens=16)
        msgs = [{"role": "user", "content": "Ответь одним словом: pong"}]
        fn = transport or (ap.gradio_call if p["kind"] == "gradio" else ap.http_openai)
        text = fn(pp, msgs, timeout, key)
    except ap.PoolError as e:
        rec.update(status=classify(e), reason=str(e)[:100], ms=int((time.time() - t0) * 1000))
        return rec
    except Exception as e:  # noqa: BLE001
        rec.update(status="net_error", reason=str(e)[:100], ms=int((time.time() - t0) * 1000))
        return rec
    ok = bool((text or "").strip())
    rec.update(status="ok" if ok else "empty", model_used=model, ms=int((time.time() - t0) * 1000), sample=(text or "").strip()[:40],
               models_total=len(ids) if ids is not None else None)
    return rec


def check_search(h):
    out = []
    base = h.env.get("NOX_SEARXNG_URL") or "http://127.0.0.1:8888"
    for name, fn in (("searxng-local", lambda: json.loads(h.http_get(base.rstrip("/") + "/search?format=json&q=test", 8))["results"]),
                     ("wikipedia", lambda: json.loads(h.http_get("https://en.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit=1&srsearch=test", 10))["query"]["search"])):
        t0 = time.time()
        try:
            r = fn()
            out.append({"name": name, "status": "ok" if r else "empty", "ms": int((time.time() - t0) * 1000)})
        except Exception as e:  # noqa: BLE001
            out.append({"name": name, "status": "net_error", "reason": str(e)[:100], "ms": int((time.time() - t0) * 1000)})
    return out


def run(registry=None, env=None, timeout=30, only=None, transport=None, models_fn=None, http_get_fn=None):
    h = hub.Hub(registry=registry, env=env, state_path=os.path.join("/tmp", "advhc_%d.json" % os.getpid()), journal=os.devnull, http_get_fn=http_get_fn)
    results = []
    for p in h.registry["providers"]:
        if only and p["name"] not in only:
            continue
        results.append(check_provider(p, h.env, timeout, transport, models_fn))
    search = check_search(h) if not only else []
    cnt = {}
    for r in results + search:
        cnt[r["status"]] = cnt.get(r["status"], 0) + 1
    ok_names = [r["name"] for r in results if r["status"] == "ok"]
    return {"id": "ADV-health", "ts": int(time.time()), "providers": results, "search": search, "counts": cnt, "ok_providers": ok_names,
            "usable": len(ok_names) >= 1, "summary": "ok=%d no_key=%d fail=%d skipped=%d" % (
                cnt.get("ok", 0), cnt.get("no_key", 0) + cnt.get("needs_free_confirm", 0), sum(v for k, v in cnt.items() if k in ("auth_fail", "rate_limited", "model_missing", "net_error", "empty")), cnt.get("skipped", 0))}


def stamp(registry_path, receipt):
    reg = json.load(open(registry_path, encoding="utf-8"))
    st = {r["name"]: r for r in receipt["providers"]}
    for p in reg["providers"]:
        r = st.get(p["name"])
        if r and r["status"] in ("ok", "auth_fail", "model_missing", "net_error", "empty", "rate_limited"):
            p["live_checked"] = r["status"] == "ok"
            p["live_ts"] = receipt["ts"]
            p["live_status"] = r["status"]
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=1)


def main(argv=None):
    ap_ = argparse.ArgumentParser()
    ap_.add_argument("--only")
    ap_.add_argument("--timeout", type=int, default=30)
    ap_.add_argument("--receipt", default="/root/nox/receipts/ADV-health.json")
    ap_.add_argument("--registry", default=os.path.join(HERE, "advisors_live.json"))
    ap_.add_argument("--stamp", action="store_true")
    a = ap_.parse_args(argv)
    rec = run(hub.load_registry(a.registry), timeout=a.timeout, only=set(a.only.split(",")) if a.only else None)
    try:
        os.makedirs(os.path.dirname(a.receipt), exist_ok=True)
        hub.statefile.write_bytes(a.receipt, json.dumps(rec, ensure_ascii=False, indent=1))
    except OSError as e:
        rec["receipt_error"] = str(e)
    if a.stamp:
        stamp(a.registry, rec)
    for r in rec["providers"] + rec["search"]:
        print("%-24s %-13s %s" % (r["name"], r["status"], r.get("reason") or ("%sms %s" % (r.get("ms"), r.get("sample", "")))))
    print(rec["summary"], "| usable" if rec["usable"] else "| NO USABLE ADVISOR (нужны ключи: см. SETUP.md)")
    return 0 if rec["usable"] else 1


if __name__ == "__main__":
    sys.exit(main())
