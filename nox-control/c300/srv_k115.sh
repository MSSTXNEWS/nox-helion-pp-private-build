echo "C300: srv_k115"
cd /workspace/nox; F=imgsvc/image_service.py
cp -n $F $F.bak_k1_flux_$(date +%Y%m%d)
python3 - <<'PY'
F="/workspace/nox/imgsvc/image_service.py"; s=open(F).read()
if "k1_flux_branch" in s: print("уже"); raise SystemExit
anchor='    model = body.get("model", "chroma")\n'
assert s.count(anchor)==1
new='''    # k1_flux_branch: ход владельца -> FLUX schnell (sd.cpp, ~35 с); chroma только по флагу uncensored/режиму без цензуры. denylist выше и NSFW/возраст-проверка после остаются всегда.
    if _k1_owner() and not body.get("uncensored") and not any(k in prompt.lower() for k in ("без цензуры", "uncensored", "no censor")):
        try:
            import sys as _s
            _s.path.insert(0, os.path.join(N, "ops", "draw"))
            import invoke_draw as _ID
            os.environ["NOX_DRAW_FORCE"] = "1"
            _t = time.time()
            _p = _ID._flux(prompt, None)
            _ID._safety_after(_p)
            return 200, {"path": _p, "seconds": round(time.time() - _t, 2), "model": "flux-schnell"}
        except Exception as _e:
            log("flux branch fail: %s" % str(_e)[:120])
            if str(_e).startswith(("запрещено", "проверка")):
                return 403, {"error": "refused", "reason": str(_e)[:120]}
'''
s=s.replace(anchor,new+anchor); open(F,"w").write(s); print("patched")
PY
python3 -m py_compile $F && echo compiled
pid=$(pgrep -f "imgsvc/image_service.py" | head -1); python3 /tmp/relaunch.py $pid /workspace/nox/imgsvc/restart_k1.log 2>&1 | tail -2
sleep 3; touch state/orch/OWNER_ACTIVE; pgrep -f "chain5|port 8199" | head -3
python3 - <<'PY'
import json,time,urllib.request
t=time.time()
try:
    r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8091/img/generate",data=json.dumps({"prompt":"a cat astronaut floating in space, stars, photo"}).encode(),headers={"Content-Type":"application/json"}),timeout=150)
    b=r.read(); st=r.status
except urllib.error.HTTPError as e: b=e.read(); st=e.code
except Exception as e: b=repr(e).encode(); st=0
print("status",st,"sec %.1f"%(time.time()-t)); print(b[:250])
PY
