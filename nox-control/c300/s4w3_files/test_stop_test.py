import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import stop_test as S
def test_static_on_fixture(tmp_path, monkeypatch):
    N = str(tmp_path); os.makedirs(N + "/web/pkg/server"); os.makedirs(N + "/agent/nox_agents")
    open(N + "/web/pkg/server/web_server.py", "w").write('if p == "/api/turn/stop":\n return CC.stop(b)\nif p == "/api/chat/stop": pass')
    open(N + "/web/pkg/server/chat_core.py", "w").write('"/v1/turns/%s/stop"\n"/v1/stop"\nt.stop = True\nc.close()\ndef _reaper_loop(): pass')
    open(N + "/agent/nox_agents/lib.py", "w").write('STOP_FILES = ("/x",)\ndef stopped(): return True\ndef llm_allowed():\n    if stopped():\n        return {"ok": False, "reason": "stopped"}\n')
    open(N + "/agent/nox_agents/a.py", "w").write("if stopped(): pass")
    monkeypatch.setattr(S, "N", N); r = S.static_path(); assert r["ok"] and r["honor_stop"] == 2 or r["honor_stop"] >= 1
def test_hands_sim_fixture(tmp_path, monkeypatch):
    N = str(tmp_path); os.makedirs(N + "/agent/nox_agents")
    open(N + "/agent/nox_agents/lib.py", "w").write('import os\nSTOP_FILES = ("/nonexistent/x",)\ndef stopped(): return any(os.path.exists(p) for p in STOP_FILES)\ndef llm_allowed():\n    if stopped():\n        return {"ok": False, "reason": "stopped"}\n    return {"ok": True}\n')
    monkeypatch.setattr(S, "N", N); r = S.hands_sim(); assert r["ok"] and r["before"] is False and r["stopped_with_flag"] is True and r["after_remove"] is False
