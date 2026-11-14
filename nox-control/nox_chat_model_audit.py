#!/usr/bin/env python3
"""NOX chat model/latency audit. Read-only by default; optional explicit Ollama warmup."""
import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

HOSTS = {
    "nox_web": "http://127.0.0.1:18775/",
    "nox_chat": "http://127.0.0.1:18877/nox/chat",
    "ollama_tags": "http://127.0.0.1:11434/api/tags",
    "ollama_running": "http://127.0.0.1:11434/api/ps",
}
def fetch(url, data=None, timeout=5):
    req = urllib.request.Request(url, data=data, headers={"Content-Type":"application/json"} if data is not None else {}, method="POST" if data is not None else "GET")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            payload = res.read(1048576)
            return {"ok":True,"http":res.status,"elapsed_ms":round((time.perf_counter()-t0)*1000),"body":json.loads(payload) if payload.startswith((b"{",b"[")) else None}
    except urllib.error.HTTPError as exc:
        return {"ok":False,"http":exc.code,"elapsed_ms":round((time.perf_counter()-t0)*1000)}
    except Exception as exc:
        return {"ok":False,"error":type(exc).__name__,"elapsed_ms":round((time.perf_counter()-t0)*1000)}

def model_summary(m):
    return {"name":m.get("name") or m.get("model"),"size":m.get("size"),"modified_at":m.get("modified_at"),"digest":m.get("digest"),"details":m.get("details")}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--warm",action="store_true",help="Send one 1-token warm-up to an already-installed Ollama model; can load GPU VRAM")
    p.add_argument("--model",default=None,help="Exact installed Ollama model name, required for --warm")
    args=p.parse_args()
    result={"checked_at":datetime.now(timezone.utc).isoformat(),"mode":"warm" if args.warm else "read_only",
            "note":"Installed/running model is NOT necessarily the model selected by NOX native OneHost router. Only request-level backend trace proves routing.",
            "services":{}}
    for key,url in HOSTS.items():
        r=fetch(url)
        result["services"][key]={k:v for k,v in r.items() if k!="body"}
        result["services"][key]["reachable"] = r.get("http") is not None
        if key=="ollama_tags":
            result["installed_models"]=[model_summary(m) for m in (r.get("body") or {}).get("models",[]) if isinstance(m,dict)]
        if key=="ollama_running":
            result["ollama_loaded_models"]=[model_summary(m) for m in (r.get("body") or {}).get("models",[]) if isinstance(m,dict)]
    result["verified_chat_model"]=None
    result["verified_model_weights_checksum"]=None
    result["verified_nox_router"]=False
    if args.warm:
        if not args.model:
            p.error("--warm requires --model EXACT_INSTALLED_MODEL")
        found={m["name"] for m in result.get("installed_models",[])}
        if args.model not in found:
            result["warmup"]={"ok":False,"reason":"MODEL_NOT_INSTALLED_EXACT_NAME"}
        else:
            payload=json.dumps({"model":args.model,"prompt":"OK","stream":False,"keep_alive":"15m","options":{"num_predict":1}}).encode()
            r=fetch("http://127.0.0.1:11434/api/generate",payload,timeout=120)
            body=r.pop("body",None) or {}
            result["warmup"]={**r,"response_model":body.get("model"),"load_duration_ns":body.get("load_duration"),"eval_duration_ns":body.get("eval_duration")}
            result["note"]="Warmup only. NOX native routing unchanged. Do not infer best model from model name or modification timestamp."
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if not result["services"]["nox_chat"]["reachable"] or not result["services"]["nox_web"]["reachable"]:
        print("ATTENTION: NOX web/chat availability incomplete; GET on a POST-only endpoint may yield 405, which does NOT prove chat is down.")
if __name__=="__main__":
    main()
