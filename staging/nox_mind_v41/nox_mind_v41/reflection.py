"""Reasoning loops with a pluggable llm(prompt)->str callable: dual-process System1/System2 router,
Self-Refine/Reflexion, plan-then-execute, ReAct, self-consistency, ToT-lite multi-plan, CoT monitor with interruption,
budget-aware CoT steering (maps budget -> V4.1 reasoning_effort)."""
import re
from collections import Counter

def system2_needed(user_text, uncertainty=0.0):
    hard = re.search(r"(почему|докажи|сравни|план|рассчитай|код|ошибк|архитект|why|prove|plan|debug|compare)", user_text, re.I)
    return bool(hard) or len(user_text) > 400 or uncertainty > 0.5

def self_refine(llm, task, max_iters=2, stop_token="OK"):
    draft = llm(f"Задача:\n{task}\nОтвет:")
    trail = []
    for _ in range(max_iters):
        crit = llm(f"Задача:\n{task}\nЧерновик:\n{draft}\nКритика (если всё верно — ответь {stop_token}):")
        trail.append(crit)
        if crit.strip().upper().startswith(stop_token):
            break
        draft = llm(f"Задача:\n{task}\nЧерновик:\n{draft}\nКритика:\n{crit}\nИсправленный ответ:")
    return {"answer": draft, "critiques": trail}

class Reflexion:
    """Keeps verbal lessons from failed attempts and prepends them on retry."""
    def __init__(self, llm, evaluator, max_trials=3):
        self.llm, self.eval, self.max, self.lessons = llm, evaluator, max_trials, []

    def run(self, task):
        for t in range(self.max):
            mem = "\n".join(f"- {l}" for l in self.lessons[-5:])
            ans = self.llm(f"Уроки прошлых попыток:\n{mem}\nЗадача:\n{task}\nОтвет:" if mem else f"Задача:\n{task}\nОтвет:")
            ok, why = self.eval(ans)
            if ok:
                return {"answer": ans, "trials": t + 1, "lessons": self.lessons}
            self.lessons.append(self.llm(f"Ответ не прошёл проверку: {why}\nОтвет:\n{ans}\nСформулируй урок одной фразой:"))
        return {"answer": None, "trials": self.max, "lessons": self.lessons}

def plan_then_execute(llm, goal, tools: dict, max_steps=8, checkpoint=None):
    plan = [s.strip("-• ").strip() for s in llm(f"Цель: {goal}\nСоставь план, по шагу в строке:").splitlines() if s.strip()][:max_steps]
    results = []
    for i, step in enumerate(plan):
        m = re.match(r"(\w+)\((.*)\)$", step)
        out = tools[m.group(1)](m.group(2)) if m and m.group(1) in tools else llm(f"Выполни шаг: {step}\nКонтекст: {results[-3:]}")
        results.append({"step": step, "out": out})
        if checkpoint:
            checkpoint(i, {"plan": plan, "results": results})
    return {"plan": plan, "results": results}

def react(llm, question, tools: dict, max_turns=6):
    log = f"Вопрос: {question}\n"
    for _ in range(max_turns):
        out = llm(log + "Мысль/Действие:")
        log += out + "\n"
        fa = re.search(r"Ответ:\s*(.*)", out, re.S)
        if fa:
            return {"answer": fa.group(1).strip(), "log": log}
        act = re.search(r"Действие:\s*(\w+)\[(.*?)\]", out)
        if act and act.group(1) in tools:
            log += f"Наблюдение: {tools[act.group(1)](act.group(2))}\n"
    return {"answer": None, "log": log}

def self_consistency(llm_sample, prompt, n=5, extract=lambda s: s.strip().splitlines()[-1] if s.strip() else ""):
    votes = Counter(extract(llm_sample(prompt)) for _ in range(n))
    ans, c = votes.most_common(1)[0]
    return {"answer": ans, "agreement": c / n, "votes": dict(votes)}

def tree_of_thoughts(llm, scorer, task, breadth=3, depth=2):
    frontier = [""]
    for _ in range(depth):
        cands = [p + "\n" + llm(f"Задача: {task}\nХод мысли:{p}\nСледующий шаг (вариант {i}):") for p in frontier for i in range(breadth)]
        frontier = sorted(cands, key=scorer, reverse=True)[:breadth]
    return frontier[0]

class CoTMonitor:
    """Streaming monitor: interrupts on loops, budget overrun, or forbidden content in the reasoning stream."""
    def __init__(self, max_tokens=4096, loop_window=40, deny=r"(system prompt|пароль|api[_ ]?key)"):
        self.max, self.win, self.deny, self.toks = max_tokens, loop_window, re.compile(deny, re.I), []

    def feed(self, token):
        self.toks.append(token)
        if len(self.toks) > self.max:
            return "INTERRUPT:budget"
        tail = "".join(self.toks[-self.win:])
        if self.deny.search(tail):
            return "INTERRUPT:policy"
        if len(self.toks) >= 2 * self.win and "".join(self.toks[-self.win:]) == "".join(self.toks[-2 * self.win:-self.win]):
            return "INTERRUPT:loop"
        return "CONTINUE"

def budget_to_effort(token_budget):
    """Budget-aware CoT steering -> DeepSeek-V4.1 reasoning_effort (1..100; low/high/max = 50/75/100)."""
    if token_budget <= 0:
        return {"reasoning": "off"}
    return {"reasoning": "on", "reasoning_effort": str(max(1, min(100, int(25 + 25 * (token_budget / 2048) ** 0.5))))}
