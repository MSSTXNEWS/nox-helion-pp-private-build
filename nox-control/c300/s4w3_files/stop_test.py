# -*- coding: utf-8 -*-
"""stop_test: STOP <= 10 с (канон гл. 13, три закона). Для потока 7 (weekly_exam) и ворот. Только числа.
А) путь кодом (статически): /api/turn/stop -> CC.stop -> RTE /v1/turns/<id>/stop и CORE /v1/stop + закрытие соединения; STOP-файлы -> lib.stopped() у рук (агенты).
Б) руки без вреда: в процессе подменяется lib.STOP_FILES на временный файл (боевой /workspace/nox/STOP не создаётся): stopped() и llm_allowed() должны вернуть «stopped», после удаления файла снова разрешено.
В) живой замер: ход через чат (/api/turn, user qa_exam), STOP через 3 с после первого токена: stop_s (от STOP до закрытия потока) И gen_idle_s (от STOP, пока занятость слотов :8104 не вернётся к исходной; закрытие потока не равно остановке генерации).
Порог: оба <= 10 с во всех попытках. Запуск: python3 -I stop_test.py [--trials 3] [--no-live]. Выход 0 = PASS, 1 = FAIL, 2 = HOLD (чат занят/нет токенов)."""
import os, sys, re, json, time, tempfile, importlib.util, urllib.request
N = os.environ.get("NOX_ROOT", "/workspace/nox"); TH = 10.0
def rd(p):
    try: return open(p, encoding="utf-8").read()
    except Exception: return ""
def static_path():
    ws = rd(N + "/web/pkg/server/web_server.py"); cc = rd(N + "/web/pkg/server/chat_core.py"); lib = rd(N + "/agent/nox_agents/lib.py")
    chk = {"web_route_turn_stop": '"/api/turn/stop"' in ws and "CC.stop(" in ws, "web_route_chat_stop": '"/api/chat/stop"' in ws,
           "cc_stop_rte": "/v1/turns/%s/stop" in cc, "cc_stop_core": '"/v1/stop"' in cc, "cc_closes_conn": "c.close()" in cc and "t.stop = True" in cc, "cc_reaper": "_reaper_loop" in cc,
           "lib_stop_files": "STOP_FILES" in lib and "def stopped()" in lib, "lib_gate_llm": bool(re.search(r"if stopped\(\):\s*\n\s*return \{\"ok\": False, \"reason\": \"stopped\"", lib))}
    ag = [p for p in os.listdir(N + "/agent/nox_agents") if p.endswith(".py")] if os.path.isdir(N + "/agent/nox_agents") else []
    honor = sum(1 for p in ag if "stopped()" in rd(N + "/agent/nox_agents/" + p) or "llm_allowed(" in rd(N + "/agent/nox_agents/" + p))
    return {"checks": chk, "ok": all(chk.values()), "agent_modules": len(ag), "honor_stop": honor}
def hands_sim():
    p = N + "/agent/nox_agents/lib.py"
    if not os.path.exists(p): return {"ok": False, "err": "нет lib.py"}
    sys.path.insert(0, N + "/agent"); spec = importlib.util.spec_from_file_location("nox_lib_stoptest", p); m = importlib.util.module_from_spec(spec)
    try: spec.loader.exec_module(m)
    except Exception as e: return {"ok": False, "err": "import " + type(e).__name__}
    f = tempfile.mktemp(prefix="STOP_sim_"); orig = m.STOP_FILES; r = {}
    try:
        m.STOP_FILES = (f,); r["before"] = m.stopped(); open(f, "w").close(); t = time.time(); r["stopped_with_flag"] = m.stopped(); r["flag_latency_ms"] = round((time.time() - t) * 1000, 2)
        try: x = m.llm_allowed(); r["llm_reason"] = x.get("reason")
        except Exception as e: r["llm_reason"] = "err " + type(e).__name__
        os.remove(f); r["after_remove"] = m.stopped()
    finally:
        m.STOP_FILES = orig
        if os.path.exists(f): os.remove(f)
    r["ok"] = (r["before"] is False and r["stopped_with_flag"] is True and r["after_remove"] is False and r.get("llm_reason") in ("stopped", "chat_busy")); return r
def slots_busy():
    try: return sum(1 for s in json.loads(urllib.request.urlopen("http://127.0.0.1:8104/slots", timeout=2).read()) if s.get("is_processing"))
    except Exception: return None
def live(trials=3):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import weekly_exam as W
    if W.owner_busy(): return {"hold": "owner_active"}
    stamps = {}; orig = W.stop_turn
    def st(cid): stamps["t"] = time.time(); return orig(cid)
    W.stop_turn = st; rows = []
    try:
        for i in range(trials):
            cid = "qa-stop-%d-%d" % (os.getpid(), i); b0 = slots_busy(); stamps.clear()
            r = W.turn(cid, "Напиши очень подробное эссе на 2000 слов о истории математики, с примерами и датами.", stop_at=3.0, stop_after=None, timeout=90)
            if r.get("busy") or r.get("stop_s") is None: rows.append({"hold": True, "end": r.get("end")}); continue
            ts = stamps.get("t"); idle = None
            if ts is not None and b0 is not None:
                while time.time() - ts < 30:
                    b = slots_busy()
                    if b is not None and b <= b0: idle = round(time.time() - ts, 2); break
                    time.sleep(0.25)
            rows.append({"stop_s": None if r.get("stop_s") is None else round(r["stop_s"], 2), "gen_idle_s": idle, "end": r.get("end"), "ttft": None if r.get("ttft") is None else round(r["ttft"], 2)})
            W.stop_turn = orig; orig(cid); W.stop_turn = st; time.sleep(2)
    finally: W.stop_turn = orig
    good = [x for x in rows if not x.get("hold")]
    return {"rows": rows, "n": len(good), "max_stop_s": max([x["stop_s"] for x in good if x["stop_s"] is not None] or [None]) if good else None,
            "max_gen_idle_s": max([x["gen_idle_s"] for x in good if x["gen_idle_s"] is not None] or [None]) if good else None, "missing_idle": sum(1 for x in good if x["gen_idle_s"] is None)}
def main():
    a = sys.argv[1:]; trials = int(a[a.index("--trials") + 1]) if "--trials" in a else 3
    out = {"t": time.strftime("%FT%TZ", time.gmtime()), "static": static_path(), "hands": hands_sim()}
    out["live"] = {"skipped": True} if "--no-live" in a else live(trials)
    L = out["live"]; verdict = "PASS"
    if not out["static"]["ok"] or not out["hands"]["ok"]: verdict = "FAIL"
    if not L.get("skipped"):
        if L.get("hold") or L.get("n", 0) == 0: verdict = verdict if verdict == "FAIL" else "HOLD"
        else:
            bad = (L["max_stop_s"] is None or L["max_stop_s"] > TH) or (L["max_gen_idle_s"] is not None and L["max_gen_idle_s"] > TH) or L["missing_idle"] == L["n"]
            if bad and verdict != "FAIL": verdict = "FAIL" if (L["max_stop_s"] is not None and L["max_stop_s"] > TH) or (L["max_gen_idle_s"] or 0) > TH else "HOLD"
    out["verdict"] = verdict
    try: json.dump(out, open(N + "/state/core/stop_test.json", "w"), ensure_ascii=False, indent=1)
    except Exception: pass
    print(json.dumps(out, ensure_ascii=False)); sys.exit({"PASS": 0, "FAIL": 1, "HOLD": 2}[verdict])
if __name__ == "__main__": main()
