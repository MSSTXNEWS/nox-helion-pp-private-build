echo "C300: srv_k103"
cd /workspace/nox; F=imgsvc/image_service.py
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/owner
curl -sfL "$R/relaunch.py?cb=$(date +%s)" -o /tmp/relaunch.py
cp -n $F $F.bak_k1_owner_$(date +%Y%m%d)
python3 - <<'PY'
F="/workspace/nox/imgsvc/image_service.py"; s=open(F).read()
if "k1_owner_ok" in s: print("уже"); raise SystemExit
old='''    return 503, {
        "error": "korea_img_disabled",
        "reason": "image generation is GB10-only while training runs",
    }
'''
new='''    # k1_owner_ok: во время хода владельца (OWNER_ACTIVE свежий) рисование локально разрешено; тренер встаёт на паузу по LIVE_TURN
    try:
        _oa = time.time() - os.path.getmtime(os.path.join(N, "state", "orch", "OWNER_ACTIVE")) < 180 and not os.path.exists(os.path.join(N, "state", "draw_local_off"))
    except OSError:
        _oa = False
    if not _oa:
        return 503, {
            "error": "korea_img_disabled",
            "reason": "image generation is GB10-only while training runs",
        }
'''
assert old in s; open(F,"w").write(s.replace(old,new)); print("patched")
PY
python3 -m py_compile $F && echo compiled
pid=$(pgrep -f "imgsvc/image_service.py" | head -1); python3 /tmp/relaunch.py $pid /workspace/nox/imgsvc/restart_k1.log 2>&1 | tail -3
sleep 3; pgrep -fa image_service | cut -c1-100
