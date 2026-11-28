import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import nox_uptime as U
def mk(tmp, state, calls, t=[1000.0]):
    os.makedirs(str(tmp) + "/state/core"); os.makedirs(str(tmp) + "/state/mind")
    ok = lambda: (True, 200, 5); ch = {k: (lambda k=k: state[k]) for k in ("tunnel", "gate", "caddy", "turn", "body", "sidecar", "voice")}
    hl = {k: (lambda k=k: calls.append(k) or 0) for k in U.ORDER}
    return U.Watch(checks=ch, healers=hl, clock=lambda: t[0], root=str(tmp)), t
GOOD = (True, 200, 5)
def good(): return {k: GOOD for k in ("tunnel", "gate", "caddy", "turn", "body", "sidecar", "voice")}
def test_all_ok_no_heal(tmp_path):
    c = []; w, t = mk(tmp_path, good(), c)
    for _ in range(5): w.step(); t[0] += 30
    assert c == []
    d = json.load(open(str(tmp_path) + "/state/core/uptime_daily.json")); assert d["chat_uptime_24h"] == 1.0
def test_body_heals_after_3_fails_only_once_per_5min(tmp_path):
    c = []; s = good(); s["body"] = (False, 0, 4); w, t = mk(tmp_path, s, c)
    for _ in range(2): w.step(); t[0] += 30
    assert c == []
    w.step(); time.sleep(0.2); assert c == ["body"]
    for _ in range(5): t[0] += 30; w.step(); time.sleep(0.05)
    assert c == ["body"]                                  # лимит 1 раз в 5 минут
    assert "heal_limit" in open(str(tmp_path) + "/state/alerts.jsonl").read()
    t[0] += 400; w.step(); time.sleep(0.2); assert c == ["body", "body"]
def test_root_cause_only(tmp_path):
    c = []; s = good(); s["body"] = (False, 0, 1); s["turn"] = (False, 599, 1); s["voice"] = (False, 0, 1); w, t = mk(tmp_path, s, c)
    for _ in range(3): w.step(); t[0] += 30; time.sleep(0.05)
    assert "body" in c and "turn" not in c
def test_voice_and_sidecar_heal_after_2(tmp_path):
    c = []; s = good(); s["voice"] = (False, 0, 1); w, t = mk(tmp_path, s, c)
    w.step(); t[0] += 30; assert c == []; w.step(); time.sleep(0.2); assert c == ["voice"]
def test_url_change_written(tmp_path):
    c = []; s = good(); s["tunnel"] = (True, 401, 9, "a-b-c.trycloudflare.com"); w, t = mk(tmp_path, s, c)
    json.dump({"lines": ["x"], "ts": 1}, open(str(tmp_path) + "/state/mind/morning_brief_v5.json", "w"))
    w.step(); p = json.load(open(str(tmp_path) + "/state/core/public_url.json")); assert p["url"] == "https://a-b-c.trycloudflare.com" and p["prev"] is None
    b = json.load(open(str(tmp_path) + "/state/mind/morning_brief_v5.json")); assert any("Адрес чата" in x for x in b["lines"]) and b["public_url"] == p["url"]
    s["tunnel"] = (True, 401, 9, "d-e-f.trycloudflare.com"); t[0] += 30; w.step(); p2 = json.load(open(str(tmp_path) + "/state/core/public_url.json")); assert p2["prev"] == p["url"] and p2["url"].endswith("d-e-f.trycloudflare.com")
    assert sum(1 for x in json.load(open(str(tmp_path) + "/state/mind/morning_brief_v5.json"))["lines"] if x.startswith("Адрес чата")) == 1
def test_metric_downtime(tmp_path):
    c = []; s = good(); w, t = mk(tmp_path, s, c)
    for i in range(200):
        s["gate"] = (i % 100 != 0, 200, 1) if True else GOOD   # 2 сбоя из 200
        w.step(); t[0] += 30
    d = json.load(open(str(tmp_path) + "/state/core/uptime_daily.json")); assert 0.98 < d["chat_uptime_24h"] < 1.0 and d["samples_24h"] == 200
def test_noheal_flag(tmp_path):
    c = []; s = good(); s["voice"] = (False, 0, 1); w, t = mk(tmp_path, s, c); open(str(tmp_path) + "/state/nox_uptime.noheal", "w").close()
    for _ in range(4): w.step(); t[0] += 30
    time.sleep(0.1); assert c == []
def test_log_has_only_codes(tmp_path):
    c = []; w, t = mk(tmp_path, good(), c); w.step(); l = open(str(tmp_path) + "/state/uptime.log").read(); assert "tunnel=200/5" in l and "http" not in l
