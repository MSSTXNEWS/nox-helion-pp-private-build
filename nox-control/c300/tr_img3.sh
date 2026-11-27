export RUNNER_TRACKING_ID=""
echo "C300: tr_img3"
N=/workspace/nox; F=$N/imgsvc/image_service.py
cp -n $F $F.bak_tr_20261127
python3 - <<'PY'
p="/workspace/nox/imgsvc/image_service.py"; s=open(p,encoding="utf-8").read()
if "TR_IMGPAUSE" in s: print("уже пропатчен")
else:
    def rep(a,b):
        global s
        assert s.count(a)==1,(s.count(a),a[:60]); s=s.replace(a,b)
    rep("def _k1_owner():\n    try:\n        return ","_FORCE = [0]  # TR_IMGPAUSE 27.11: >0 пока идёт генерация с паузой тренера\ndef _k1_owner():\n    if _FORCE[0] > 0: return not os.path.exists(os.path.join(N, \"state\", \"draw_local_off\"))\n    try:\n        return ")
    rep("    if not _oa:\n        return 503, {","    if not (_oa or _FORCE[0] > 0):\n        return 503, {")
    rep("def handle_generate(body):\n","def handle_generate(body):\n    \"\"\"TR_IMGPAUSE: запрос рисования ставит тренер на паузу (SIGSTOP), генерирует FLUX, возвращает тренера (SIGCONT). Откат: touch state/img_pause_off.\"\"\"\n    if os.path.exists(os.path.join(N, \"state\", \"img_pause_off\")): return handle_generate_orig(body)\n    import signal as _sg\n    stopped = []\n    try:\n        out = subprocess.run([\"pgrep\", \"-f\", r\"train_dpo\\.py|distill_v2\\.py train|rel_gates\\.py|gates_only\\.py\"], capture_output=True, text=True).stdout.split()\n        for x in out:\n            pid = int(x)\n            try: st = open(\"/proc/%d/stat\" % pid).read().rsplit(\")\", 1)[1].split()[0]\n            except Exception: continue\n            if \"python\" not in open(\"/proc/%d/cmdline\" % pid, \"rb\").read().decode(\"utf-8\", \"replace\"): continue\n            if st != \"T\":\n                try: os.kill(pid, _sg.SIGSTOP); stopped.append(pid)\n                except Exception: pass\n        _t0 = time.time()\n        while time.time() - _t0 < 10:   # SIGSTOP не освобождает VRAM: ждём до 10 с, затем генерируем\n            try:\n                u, tt = vram_used_mib()\n                if u / max(tt, 1) <= 0.92: break\n            except Exception: break\n            time.sleep(1)\n        log(\"IMGPAUSE stopped=%d\" % len(stopped))\n        _FORCE[0] += 1\n        return handle_generate_orig(body)\n    finally:\n        _FORCE[0] = max(0, _FORCE[0] - 1)\n        for pid in stopped:\n            try: os.kill(pid, _sg.SIGCONT)\n            except Exception: pass\n        if stopped: log(\"IMGPAUSE resumed=%d\" % len(stopped))\ndef handle_generate_orig(body):\n")
    open(p,"w",encoding="utf-8").write(s); print("пропатчен")
PY
python3 -m py_compile $F && echo "компиляция ok"; sed -n 100,109p $F | cut -c1-160
supervisorctl status 2>&1 | grep -i -E "img|image" | head -3
echo END
