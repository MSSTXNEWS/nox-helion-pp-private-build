"""health_probe: HTTP probes of NOX services (web 8091, embeddings 8082, bridge/llama 8098)."""
import os
import time
import registry as R


def defaults():
    return [
        {"name": "web8091", "urls": [os.environ.get("NOX_WEB_URL", "http://127.0.0.1:8091") + "/api/health", "http://127.0.0.1:8091/health"]},
        {"name": "embed8082", "urls": [os.environ.get("NOX_EMBED_URL", "http://127.0.0.1:8082") + "/health"]},
        {"name": "bridge", "urls": [os.environ.get("NOX_BRIDGE_URL", "http://127.0.0.1:8098") + "/health"]}]


@R.register("health_probe", "read", {"properties": {
    "targets": {"type": "array", "description": "[{name, url}] overrides defaults"},
    "timeout": {"type": "number", "default": 3}}}, "Probe service health endpoints; returns per-target up/down, status, ms.")
def health_probe(a):
    targets = [{"name": t["name"], "urls": [t["url"]]} for t in a["targets"]] if a.get("targets") else defaults()
    out = []
    for t in targets:
        r = {"name": t["name"], "up": False}
        for u in t["urls"]:
            t0 = time.time()
            st, _ = R.http_json(u, timeout=a["timeout"])
            r.update(url=u, status=st, ms=int((time.time() - t0) * 1000))
            if 200 <= st < 300:
                r["up"] = True
                break
        out.append(r)
    return {"ok": all(r["up"] for r in out), "targets": out}
