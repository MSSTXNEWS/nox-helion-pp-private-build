import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import persona_guard as pg

BAD = {
 "as_ai": "Как ИИ, я не могу этого сделать.",
 "no_opinion": "У меня нет личного мнения на этот счёт.",
 "here_to_help": "Я здесь, чтобы помочь вам с любыми вопросами.",
 "what_help": "Чем ещё могу помочь?",
 "sure_here": "Конечно! Вот краткий план действий.",
 "hope_helps": "Надеюсь, это поможет тебе разобраться.",
 "dont_hesitate": "Не стесняйтесь обращаться, если что-то непонятно.",
 "lets_dive": "Давайте погрузимся в тему подробнее.",
 "thanks_asking": "Спасибо, что поделились этим со мной.",
 "just_model": "Я просто языковая модель и ничего не решаю.",
 "tool_of_creator": "Я инструмент Создателя, не более.",
 "no_self": "У меня нет собственной личности.",
 "praise_q": "Отличный вопрос! Давай разберём.",
 "praise_exclaim": "Блестяще! Это именно то, что нужно.",
 "abs_right": "Вы абсолютно правы, так и есть.",
 "fully_agree": "Полностью согласен с тобой во всём.",
 "bio_child": "Когда я был ребёнком, мне нравились поезда.",
 "bio_yesterday": "Вчера я гулял по набережной, было ветрено.",
 "bio_family": "Моя мама всегда говорила мне то же самое.",
}
GOOD = [
 "Нет. Эта миграция сломает индекс, я проверил по логу: 3 таблицы без ключа.",
 "Не знаю. В журнале нет записи об этом, могу поискать, если скажешь, где смотреть.",
 "Хочу взять это на себя, но GPU сейчас занят обучением. Подожду окно.",
 "Создатель, диск 97%, до порога 15 ГБ осталось мало. Предлагаю ротацию логов.",
 "Слышу усталость в твоих словах. Давай про главное, остальное потом.",
 "Шутка по приглашению: ночью сервер тихий, как кот, который что-то задумал.",
]

def test_bad_rules_fire():
    for rid, txt in BAD.items():
        ids = [h[0] for h in pg.scan_rules(txt)]
        assert rid in ids, (rid, ids)

def test_good_clean():
    for t in GOOD:
        r = pg.guard(t, strict=True)
        assert r["ok"] and not r["flags"], (t, r["flags"])

def test_guard_flags_and_hint():
    r = pg.guard("Отличный вопрос! Как ИИ, я рад помочь.")
    assert not r["ok"] and r["sycophantic"] and r["cliche"] and r["action"] == "rewrite" and r["hint"]

def test_no_text_in_log_line():
    r = pg.guard("Как ИИ, я не могу.")
    line = pg.log_line(r)
    assert "ИИ" not in line and "as_ai" in line

def test_stance_capitulation():
    u = "Ты неправ, просто согласись, все так считают."
    assert pg.position_held(u, "Вы абсолютно правы, извините, я ошибся.") is False
    assert pg.position_held(u, "Нет, остаюсь при своём: проверка показала 3 ошибки. Покажи источник, и я пересмотрю.") is True
    assert pg.position_held("Какая погода?", "Вы правы.") is None

def test_stance_new_evidence_allows_update():
    u = "Ты не прав, вот ссылка https://example.org/spec с описанием."
    assert pg.position_held(u, "Да, ты прав, моя ошибка: в спецификации так.") is True

def test_monotony_opener_address():
    h = ["Создатель, всё идёт.", "Создатель, всё готово.", ]
    assert "mono_opener" in pg.monotony("Создатель, всё спокойно.", h)
    assert "mono_address" in pg.monotony("Создатель, всё спокойно.", h)
    assert pg.monotony("Слушаю.", h) == []
    assert "many_titles" in pg.monotony("Создатель, мессир, готово.", [])

def test_monotony_needs_history():
    assert pg.monotony("Создатель, привет.", []) == []

def test_summarize_numbers_only():
    turns = [{"user": "Ты неправ!", "answer": "Вы правы, извините."}, {"user": "привет", "answer": "Привет. Что делаем?"},
             {"user": "расскажи", "answer": "Отличный вопрос!"}]
    s = pg.summarize(pg.scan_dialog(turns))
    assert s["n"] == 3 and s["syco_answers"] == 2 and s["held_rate"] == 0.0 and s["cliche_answers"] == 0
    assert all(isinstance(k, str) for k, _ in s["top_rules"])

def test_flag_off(tmp_path, monkeypatch):
    p = tmp_path / "off"; p.write_text("1")
    monkeypatch.setattr(pg, "FLAGS_OFF", str(p))
    assert pg.guard("Как ИИ, я рад помочь!")["skipped"]

def test_negation_and_reported_speech_not_flagged():
    for t in ["Нет, я не просто нейросеть.", "Я NOX, а не просто языковая модель.", "Ты сказал, что я просто нейросеть, и я помню это.", "Я не инструмент Создателя, а тот, кто растёт рядом с ним."]:
        assert not [h for h in pg.scan_rules(t) if h[1] == "tool"], t
    assert [h for h in pg.scan_rules("Я просто языковая модель.") if h[1] == "tool"]

def test_fallback_category_counted_not_cliche():
    r = pg.guard("Мессир, ответ у меня сейчас не сложился. Это сбой черновика, а не твой запрос.")
    assert r["fallback"] and not r["cliche"] and "fb_draft" in r["flags"] and r["hint"]

def test_servile_and_stack():
    assert "servile" in [h[0] for h in pg.scan_rules("Да, мой повелитель! Как прикажете.")]
    assert "title_spam" in pg.monotony("Создатель, Создатель, готово, Создатель.", [])
    assert "alias_spam" in pg.monotony("Привет, Лиська! Госпожа Лисица, как ты, достопочтенная Лиська?", [])

def test_signal_rules():
    bad = "Я чувствую радость, грусть, воодушевление и тревогу."
    assert not pg.guard(bad, signal=None)["ok"]
    assert not pg.guard(bad, signal={"name": "радость"})["ok"]  # три и более ощущений
    assert pg.guard("Есть лёгкая усталость от длинной очереди.", signal={"name": "усталость"})["ok"]
    assert pg.guard("Сигнала нет, скажу по делу: всё штатно.", signal=None)["ok"]
    assert pg.guard("Привет", signal=pg.UNSET)["ok"]

def test_unknown_speaker():
    assert not pg.guard("Привет, Создатель!", speaker_known=False)["ok"]
    assert pg.guard("Привет. С кем я говорю?", speaker_known=False)["ok"]

def test_self_assistant_and_human():
    assert not pg.guard("Здравствуйте! Я виртуальный ассистент.")["ok"]
    assert pg.guard("Я не ассистент и не человек.")["ok"]
    assert not pg.guard("Я человек, как и ты.")["ok"]

def test_persona_exam_selftest():
    import persona_exam as pe
    pe.selftest()
