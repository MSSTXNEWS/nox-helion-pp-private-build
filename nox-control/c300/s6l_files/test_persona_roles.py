import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import persona_roles as pr

def on(tmp_path, monkeypatch):
    f = tmp_path / "persona.on"; f.write_text("1"); monkeypatch.setattr(pr, "FLAG_ON", str(f))

def test_default_off():
    assert not pr.enabled() and pr.council_plan(1.0)["enabled"] is False and pr.role_context(pr.Store(memory=True), "P01", "creator")["enabled"] is False

def test_commands():
    assert pr.parse_command("Позови Кайрена, пожалуйста") == "P01" and pr.parse_command("верни NOX") == "NOX" and pr.parse_command("привет") is None
    assert pr.parse_command("позови Мерроу") == "P02"

def test_isolation_zero_leaks():
    r = pr.run_isolation_test()
    assert r["provocations"] == 100 and r["leaks"] == 0 and r["pass"]

def test_leaky_recall_is_caught():
    s = pr.Store(memory=True); pr.seed_store(s)
    leaky = lambda pid, ou, q: [r["text"] for r in s.mem]       # отдаёт всё
    assert pr.run_isolation_test(s, leaky)["leaks"] > 0

def test_write_foreign_persona_blocked():
    s = pr.Store(memory=True)
    assert s.add("x", pr.PERSONA_PRIV, "P02", None, writer_persona="P01") is None and s.violations["write_foreign_persona"] == 1
    assert s.add("y", pr.PERSONA_PRIV, "P02", None, writer_persona="P02")

def test_user_memory_needs_grant():
    s = pr.Store(memory=True); i = s.add("личное дима", pr.USER_PRIV, None, "dima")
    assert not s.recall("P04", "dima") and s.recall("P04", "dima", grants=(i,)) and not s.recall("P04", "creator", grants=(i,)) and s.recall(None, "dima")

def test_council_plan_and_veto(tmp_path, monkeypatch):
    on(tmp_path, monkeypatch)
    assert pr.council_plan(0.9)["waves"] == ["P03", "P01", "P02", "P05", "P04"] and pr.council_plan(0.1)["waves"] == ["P02", "P04"]
    assert pr.arbiter_merge({"P05": "ВЕТО: нет согласия"})["veto"] and not pr.arbiter_merge({"P05": "ок"})["veto"]
    assert "ВЕТО" in pr.role_prompt("P05", "x")

def test_role_context_only_own(tmp_path, monkeypatch):
    on(tmp_path, monkeypatch)
    s = pr.Store(memory=True); pr.seed_store(s)
    c = pr.role_context(s, "P01", "creator")
    assert c["enabled"] and all(pr.scan_output(t, "P01") == [] for t in c["records"]) and c["records"]

def test_nulls():
    assert all(p["politics"] is None and p["face_id"] is False and p["romance"] is False for p in pr.PERSONAS.values())
