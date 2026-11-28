import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import interlocutor_model as im

def mk(user="creator"): return im.Model(user)
NOW = 1_800_000_000.0

def test_pad_decay_and_label():
    m = mk(); m.update({"ts": NOW, "text": "ужасно устал, всё опять не работает!!", "user": "creator"})
    s = m.state(NOW + 60)
    assert s["pad"]["v"] < -0.1 and s["fatigue"] > 0
    s2 = m.state(NOW + 10 * 3600); assert s2["conf"] < s["conf"] and abs(s2["pad"]["v"]) <= abs(s["pad"]["v"]) or s2["conf"] == 0

def test_foreign_user_events_rejected():
    m = mk("dima"); assert m.update({"ts": NOW, "text": "личное создателя", "user": "creator"}) is False and not m.events

def test_goals_and_promises():
    m = mk(); m.update({"ts": NOW, "text": "Напомни завтра проверить диск и обучение адаптера", "user": "creator"})
    m.update({"ts": NOW + 5, "text": "Хочу ускорить обучение адаптера", "user": "creator"})
    g = m.goals(NOW + 3600); assert g["open"] and any("обучен" in t or "адаптер" in t for t in g["topics"])

def test_forecast_tired_long_negative():
    m = mk(); m.update({"ts": NOW, "text": "очень устал, нет сил, срочно коротко", "user": "creator"})
    long = " ".join(["слово"] * 200)
    f = m.forecast(long, NOW + 30); g = m.forecast("Диск 26 ГБ, порог 15. Ротация логов?", NOW + 30)
    assert f["valence"] < g["valence"] and f["advice"]

def test_cliche_lowers_forecast():
    m = mk(); a = m.forecast("Отличный вопрос! Как ИИ, я рад помочь.", NOW); b = m.forecast("Диск 26 ГБ. Предлагаю ротацию.", NOW)
    assert a["valence"] < b["valence"] and "убрать клише и лесть" in a["advice"]

def test_observe_learns():
    m = mk(); d = "Отличный вопрос! Как ИИ, я рад помочь."
    before = m.forecast(d, NOW)["valence"]
    for i in range(12): m.observe(d, "бесит, опять шаблон, надоел", NOW + i)
    assert m.forecast(d, NOW)["valence"] < before and m.mean_surprise() is not None

def test_save_load_roundtrip(tmp_path):
    m = mk(); m.update({"ts": NOW, "text": "хочу закончить обучение", "user": "creator"}); p = str(tmp_path / "t.json"); m.save(p)
    m2 = im.Model.load("creator", p); assert m2.events and m2.open_items

def test_block_short_no_texts():
    m = mk(); m.update({"ts": NOW, "text": "хочу закончить обучение адаптера", "user": "creator"})
    b = m.block(NOW + 60); assert len(b) < 200 and "creator" in b

def test_from_feed_tolerant():
    ls = ['{"ts": 1800000000, "text": "спасибо, отлично!", "user_id": "dima"}', 'not json', '{"content": {"user": "устал"}, "t": "2027-01-15T08:00:00Z"}']
    m = im.from_feed("dima", ls); assert len(m.events) >= 1
