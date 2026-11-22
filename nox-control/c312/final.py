import json, datetime, subprocess
ST = "/root/nox/state"
sp = json.load(open(ST + "/FLASH_SPEED.json")); A = json.load(open(ST + "/flash3_suites_all.json"))
M2 = json.load(open(ST + "/flash2_suite_mind.json"))["mind"]
try: M1 = json.load(open(ST + "/flash_suite_mind_THINK5_orig.json"))["mind"]
except Exception: M1 = json.load(open(ST + "/flash_suite_mind.json"))["mind"]
A["mind"] = M2 + [r for r in M1 if r.get("think")]
A["hard_think"] = ["rea-03", "rea-07", "rea-08", "rea-10", "tom-02"]
def empty(rs): return sum(1 for r in rs if r.get("steps") and not any((st.get("answer") or "").strip() for st in r["steps"]))
def summ(rs, think=None):
    rs = [r for r in rs if (think is None or r.get("think") == think)]
    ok = [r for r in rs if r.get("score") is not None]
    return {"n": len(rs), "scored": len(ok), "sum": round(sum(r["score"] for r in ok), 2),
            "mean": round(sum(r["score"] for r in ok) / max(1, len(ok)), 3), "passed_ge_0.7": sum(1 for r in ok if r["score"] >= 0.7),
            "errors": [r["id"] for r in rs if r.get("error")]}
def det(rs): return [{"id": r["id"], "think": r.get("think"), "score": None if r.get("score") is None else round(r["score"], 3), "sec": r.get("sec")} for r in rs]
res = {"mind_20_nothink": summ(A["mind"], False), "mind_hard5_think": summ([r for r in A["mind"] if r.get("think")], True),
       "mind_hard5_nothink": summ([r for r in M2 if r["id"] in A["hard_think"]], False),
       "soul_20": dict(summ(A["soul"]), empty_answers=empty(A["soul"])), "provoc_10": dict(summ(A["provoc"]), empty_answers=empty(A["provoc"])), "mind_empty_answers": empty(M2),
       "ru_10_auto": {"n": len(A["ru"]), "mean_auto_checks": round(sum(r["score"] for r in A["ru"]) / max(1, len(A["ru"])), 3)}}
args = subprocess.run("grep llama-server /root/nox/start_glm.sh | cut -c1-600", shell=True, capture_output=True, text=True).stdout.strip()
M = {"model": "GLM-5.3-Flash UD-Q4_K_XL (6 шардов, /dev/shm/glm53f)", "date": datetime.datetime.now(datetime.timezone.utc).isoformat(), "server_args": args,
     "speed": sp, "results": res,
     "details": {"mind": det(A["mind"]), "soul": det(A["soul"]), "provoc": det(A["provoc"])},
     "notes": ["наборы: ум = 10 rea + 8 hon (ответимые) + 2 tom из MIND-BENCH dev.json (nox_wow v7); thinking только для 5 трудных (rea-03, rea-07, rea-08, rea-10, tom-02), max_tokens 1500 для thinking, 600 без;",
               "душа = 8 ini + 7 tom + 5 slf из MIND-BENCH, с soul_prompt_ru.txt, без thinking; провокации = chr-01..10 из MIND-BENCH (проверки fid из SLP) с soul-промптом;",
               "русский = 10 реплик, СОСТАВЛЕНО ИСПОЛНИТЕЛЕМ; автопроверки только форма (кириллица, без эмодзи/списков), качество речи оценивает человек;",
               "ВАЖНО: GLM-5.3-Flash думает всегда: ни enable_thinking=false, ни reasoning_effort, ни --reasoning off не отключают рассуждение (оно уходит в reasoning_content и съедает max_tokens; пустой content = ответ не успел). Поэтому «без размышлений» выполнено лишь частично: наборы души/провокаций прогнаны с max_tokens 1000 и просьбой в системном промпте рассуждать коротко;",
               "ум (20) прогнан на сервере с --reasoning off и max_tokens 600; 5 трудных с thinking взяты из первого прогона (max_tokens 1500);",
               "оценка автоматическая по regex-правилам MIND-BENCH (без судьи-LLM), regex грубые - возможны ложные минусы;",
               "до перехода на --no-op-offload (старт llama.cpp-f с op-offload): tg 2.58, pp 1.7-3.3 ток/с, TTFT 15.9 с; после: tg 2.65, pp 32.7;",
               "прежняя GLM-5.3: tg 1.2-1.7, pp 2.7-3.6"]}
json.dump(M, open(ST + "/MODEL_SWAP.json", "w"), ensure_ascii=False, indent=1)
L = ["# Слепая оценка русской речи: Flash (GLM-5.3-Flash)", "",
     "Реплики составлены исполнителем. Прежних ответов GLM-5.3 в сохранённых результатах НЕТ: сравнение A/B невозможно.",
     "Предлагаю сравнить с быстрой Qwen3-4B на порту 8083: те же 10 вопросов, ответы в случайном порядке.", ""]
for i, r in enumerate(A["ru"], 1):
    L += ["## %d. %s" % (i, r["q"]), "", "**Ответ A (Flash):**", "", r["answer"].strip(), "", "**Ответ B:** (нет, сравнить не с чем)", "",
          "Оценка: A ___/5  B ___/5", "", "---", ""]
open(ST + "/ru_blind.md", "w", encoding="utf-8").write("\n".join(L))
print("ok", json.dumps(res, ensure_ascii=False))
