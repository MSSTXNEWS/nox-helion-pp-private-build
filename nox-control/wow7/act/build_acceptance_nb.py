#!/usr/bin/env python3
"""ACT/acceptance_nb.json: 12 сценариев «Живой NOX» (living_12) + 44 инфраструктурных кейса NOX-100 (nox100_plan) как спецификации
НАТИВНОЙ приёмки (state=NOT_RUN: результаты принимаются только из живых квитанций). Читает недоверенный JSON как данные.
Запуск: python3 -I build_acceptance_nb.py <каталог brain_vnext> [out]"""
import json, os, sys
SRC = sys.argv[1] if len(sys.argv) > 1 else "/home/claude/drive_brain/brain_vnext"
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "acceptance_nb.json")

# что у нас уже проверяет то же самое без живого сервера (tool) и какая часть остаётся нативной
LV = {
 "LV-01": ("MIND/M4_BENCH nb-MEM-02-*, nb-MEM-01-*; GENOME nb.fact_supersede", "чтение версии из S03 после смены устройства"),
 "LV-02": ("GENOME nb.forget_request; MEM/correction.py (отзыв); MIND/M4_BENCH nb-MEM-03-*", "перезапуск потребителя и вход модели после отзыва"),
 "LV-03": ("MIND/M4_BENCH nb-SOUL-01-*, nb-SOUL-04-*; MIND/R2/anti_sycophancy.py", "слепая оценка парных сценариев"),
 "LV-04": ("MIND/M4_BENCH nb-SOUL-03-*; EMO/appraisal.py (журнал причин)", "запись перехода состояния на живом ядре"),
 "LV-05": ("MIND/M4_BENCH nb-INIT-04-*; GENOME consents + ini.*", "событие предложения и новая эпоха согласия"),
 "LV-06": ("GENOME nb.fiction_separation; CONCEPT_FICTION_50.md", "два scoped снимка профилей"),
 "LV-07": ("MIND/M4_BENCH nb-GROW-02-*; GENOME nb.reflection_mode; MIND/M5_GROWTH", "день между прогонами и независимая проверка"),
 "LV-08": ("GENOME nb.belief_revision; MIND/M4_BENCH nb-REASON-02-*", "противоречивые источники на живом поиске"),
 "LV-09": ("ACT/pv01_e2e.py (resume/SSE); BRAIN/test_core.py", "обрыв SSE в полном чате и мини-чате"),
 "LV-10": ("BRAIN/nox_core.py stop_turn (квитанция slot-idle); ACT/pv01_e2e.py step_stop", "голосовое перебивание на устройстве"),
 "LV-11": (None, "нет прямого аналога в пакете: режим «форсаж» 3->6->3 проверяется только на живой очереди S1"),
 "LV-12": ("DSP/nox_dispatcher.py + DSP/test_dsp.py (lease/поколения)", "имитация обрыва до/после сохранения на тестовой эстафете"),
}
# инфраструктурные семейства NOX-100 (не оцениваются по тексту): как измерять и чем у нас
INFRA = {
 "latency": ("холодный/тёплый, короткий/длинный запрос измеряются отдельно; первый содержательный токен отдельно от полного ответа", "SPD/ab_bench.py", "p50/p95 TTFT и tg по классам; нет смешения холодного и тёплого"),
 "long_prefix": ("длинный префикс: прирост от prefix/KV-кэша и отзыв кэша", "SPD/ab_bench.py; OPT/semantic_cache.py", "reuse_tokens>0 на втором запросе; после отзыва записи кэш не отдаёт её"),
 "resume_and_stop": ("обрыв SSE -> возобновление с Last-Event-ID; STOP конкретного ответа", "ACT/pv01_e2e.py; BRAIN/nox_core.py", "один логический обмен и одна квитанция; после terminal cancel новых записей нет"),
 "voice_barge_in": ("перебивание голосом: остановка звука и отмена старых действий измеряются отдельно", "DSP; SELF; BRAIN stop_turn", "время до тишины и отдельная проверка side effects"),
 "routing": ("маршрутизация быстрый/глубокий без тихой подмены модели", "MIND/M1_ARCH/solver_policy.py; BRAIN/executors.py", "реальный маршрут в квитанции совпадает с заявленным"),
 "verification_budget": ("бюджет проверки: одна доп. проверка по необходимости, не на каждый ход", "MIND/M1_ARCH; BRAIN/conscience.py", "число проверок <= бюджета; формальные ограничения проверяются кодом"),
 "notification_dedupe": ("повторное событие не даёт второго уведомления", "ACT/task_runner.py (идемпотентный submit); GENOME limits cooldown", "ровно одно уведомление на событие после ретрая"),
 "resume_confirmed_work": ("после обрыва не повторять подтверждённые шаги", "ACT/task_runner.py (журнал, replay); acceptance_10.json", "завершённые шаги не исполняются повторно"),
 "one_verified_effect": ("один разрешённый шаг -> один подтверждённый эффект", "ACT/task_runner.py; ACT/acceptance_10.json", "эффект один, перепроверка живая, откат побайтно"),
 "held_out_examples": ("улучшение проверяется на новых примерах вне обучающих шаблонов", "MIND/M4_BENCH holdout; MIND/R2/gate_all.py", "gate принимает только при приросте на holdout без регресса"),
 "rollback": ("откат неудачного изменения: состояние как до", "SLP (rollback); MIND/M2_SELFIMPROVE; ACT откат x2", "хеши до и после отката совпадают"),
}

def main():
    lv = json.load(open(os.path.join(SRC, "living_12.json"), encoding="utf-8"))
    plan = json.load(open(os.path.join(SRC, "nox100_plan.json"), encoding="utf-8"))
    items = []
    for c in lv["cases"]:
        tool, native = LV[c["id"]]
        items.append({"id": "NB-" + c["id"], "kind": "living12", "source": "living_12.json:" + c["id"], "lane": c["role"], "title": c["title"],
                      "input": c["input"], "pass_if": c["pass_if"], "evidence": c["evidence"],
                      "covered_offline_by": tool, "native_remainder": native, "state": "NOT_RUN", "native_result": None})
    seen = set()
    for c in plan["cases"]:
        if c["family"] not in INFRA:
            continue
        how, tool, ok = INFRA[c["family"]]
        items.append({"id": "NB-" + c["id"], "kind": "nox100_infra", "source": "nox100_plan.json:" + c["id"], "lane": c["lane"], "family": c["family"],
                      "language": c["language"], "variant": c["variant"], "how": how, "covered_offline_by": tool, "pass_if": ok,
                      "evidence": c["evidence"], "state": "NOT_RUN", "native_result": None})
        seen.add(c["family"])
    assert seen == set(INFRA), seen ^ set(INFRA)
    out = {"schema": "nox_acceptance_nb_v1", "note": "Спецификации нативной приёмки. state=NOT_RUN у всех: принимать только по живым квитанциям (S03, браузер, STOP). Текстово-оценимые 56 кейсов NOX-100 — в MIND/M4_BENCH/tasks/nb100.json. Исполнимая офлайн-приёмка действий — acceptance_10.json (task_runner).",
           "counts": {"living12": 12, "nox100_infra": len(items) - 12, "nox100_text_in_m4": 56}, "items": items}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(OUT, out["counts"])

if __name__ == "__main__":
    main()
