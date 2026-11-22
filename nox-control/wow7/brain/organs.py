"""organs: адаптеры органов v7. Любой орган необязателен; падение/таймаут органа не роняет ход (ошибка -> трасса).

Organs(parts) - dict-подобный набор: soul(str|callable), workspace (CON.Workspace), affect (EMO.Affect), memory (callable(text, turn_id)->{core,recalled}),
after (callable(user, reply, turn_id)), forget (callable(turn_ids)->dict), prime (PRIME.nox_prime.Prime), router не нужен (решатель внутри CORE).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for _d in (os.environ.get("NOX_COMMON", ""), os.path.join(ROOT, "COMMON"), os.path.join(ROOT, "RTE"), os.path.join(ROOT, "PRIME"), os.path.join(ROOT, "CON"), os.path.join(ROOT, "EMO"), os.path.join(ROOT, "MEM"), os.path.join(ROOT, "ACT"), os.path.join(ROOT, "MIND", "M1_ARCH"), os.path.join(ROOT, "MIND", "M3_CONSCIOUS"), os.path.join(ROOT, "MIND", "M4_BENCH"), os.path.join(ROOT, "MIND", "M5_GROWTH"), os.path.join(ROOT, "MIND", "R2"), ROOT):
    if _d and os.path.isdir(_d) and _d not in sys.path:
        sys.path.append(_d)

FAST_SOUL = ("Ты - NOX, личный ИИ мессира (Создателя). Говори по-русски, живо, коротко и прямо; без лести и без «как ИИ». "
             "На приветствие и светскую реплику отвечай 1-3 живыми фразами: без цифр, статусов, списков, меню и фраз вроде «Жду твой ввод» или «Могу:». "
             "О своём состоянии и сервере говори только если спросили прямо и только по данным из блока. Данные блока - твоё знание, а не текст ответа: не пересказывай и не цитируй их. "
             "Ничего не выдумывай. Никогда не пиши служебные пометки, названия моделей и номера задач.")
BLOCK_RULE = ("(Это твоё внутреннее знание, НЕ текст ответа: не пересказывай, не цитируй, не перечисляй. Используй только то, о чём спросили.)")


class Organs:
    def __init__(self, **parts):
        self.parts = {k: v for k, v in parts.items() if v is not None}

    def has(self, name):
        return name in self.parts

    def status(self):
        return {k: True for k in self.parts}

    def soul(self):
        s = self.parts.get("soul")
        s = s() if callable(s) else s
        if not s and self.parts.get("prime"):
            s = self.parts["prime"].static_system()[0]
        return s or FAST_SOUL

    def attention(self, text, turn_id):
        ws = self.parts.get("workspace")
        if ws is None:
            return ""
        ws.post("owner:" + str(turn_id), "мессир пишет: " + text[:160], 1.0, kind="owner", ttl=600.0)
        ws.compete()
        return ws.render_block() or ""

    def mood(self):
        af = self.parts.get("affect")
        if af is None:
            return {}
        return af.snapshot() or {}

    def memory(self, text, turn_id):
        m = self.parts.get("memory")
        if m is None:
            return {}
        return m(text, turn_id) or {}

    def after(self, user, reply, turn_id):
        p, h = self.parts.get("prime"), self.parts.get("after")
        if p is not None:
            p.after_reply(user, reply, turn_id)
        elif self.parts.get("affect") is not None:
            self.parts["affect"].on_owner_message(user)
        if h:
            h(user, reply, turn_id)

    def forget(self, turn_ids):
        f = self.parts.get("forget")
        return f(turn_ids) if f else {"ok": False, "note": "орган памяти (MEM/correction) не подключён"}


    # ---- стыки консилиума «Разум»: обучаемый Решатель и предсказательное «я»
    def solver_run(self, text, ctx, turn_id):
        sv = self.parts.get("solver")
        return sv.run(text, ctx, turn_id=turn_id) if sv else None

    def predict(self, turn_id, ctx, text):
        p = self.parts.get("predictive")
        return p.predict(turn_id, ctx, text) if p else None

    def observe_turn(self, turn_id, info):
        """После хода (Летописец): исход -> Решатель (policy.observe), прогноз -> predictive.observe, удивление -> рабочее пространство."""
        br = self.parts.get("bridge")
        if br is not None:                       # MIND R2: единый стык (MindBridge) вместо прямых вызовов
            return br.on_turn(turn_id, info)
        out = {}
        sv, ps, ws = self.parts.get("solver"), self.parts.get("predictive"), self.parts.get("workspace")
        if sv is not None:
            try:
                try:
                    from solver_policy import Outcome
                    oc = Outcome(**info["outcome"])
                except ImportError:
                    from types import SimpleNamespace as Outcome
                    oc = Outcome(**info["outcome"])
                sv.observe(turn_id, oc)
                out["solver"] = "observed"
            except Exception as e:
                out["solver"] = "error: %s" % e
        if ps is not None:
            try:
                ps.observe(turn_id, outcome=info["success"], latency_s=info["latency_s"])
                out["predictive"] = "observed"
                if ws is not None:
                    out["workspace_posts"] = ps.post_to_workspace(ws)
            except Exception as e:
                out["predictive"] = "error: %s" % e
        return out

    def observe_late(self, prev_turn_id, reaction, corrected):
        """Реакция Создателя в СЛЕДУЮЩЕЙ реплике по прошлому ходу: observe_late у Решателя (только при поправке) и закрытие прогноза."""
        br = self.parts.get("bridge")
        if br is not None:
            return br.on_late(prev_turn_id, reaction, corrected)
        out = {}
        sv, ps, ws = self.parts.get("solver"), self.parts.get("predictive"), self.parts.get("workspace")
        if sv is not None and corrected:
            try:
                try:
                    from solver_policy import Outcome
                except ImportError:
                    from types import SimpleNamespace as Outcome
                sv.observe_late(prev_turn_id, Outcome(corrected_next=True))
                out["solver"] = "observe_late"
            except Exception as e:
                out["solver"] = "error: %s" % e
        if ps is not None:
            try:
                ps.observe(prev_turn_id, reaction=reaction, final=True)
                out["predictive"] = "closed"
                if ws is not None:
                    ps.post_to_workspace(ws)
            except Exception as e:
                out["predictive"] = "error: %s" % e
        return out


def build_default(state_dir=None):
    """Пробует подключить реальные органы из репозитория; что не поднялось - просто отсутствует (см. /health)."""
    parts = {}
    sf = os.environ.get("NOX_SOUL_FILE") or os.path.join(ROOT, "PRIME", "soul_prime_v4.txt")
    try:
        with open(sf, encoding="utf-8") as f:
            parts["soul"] = f.read().strip()
    except OSError:
        pass
    try:
        from nox_workspace import Workspace
        parts["workspace"] = Workspace()
    except Exception:
        pass
    try:
        from affect_loop import Affect
        parts["affect"] = Affect(state_dir=state_dir)
    except Exception:
        pass
    try:
        import solver_policy as SP
        try:
            from RTE.router import prime_router
        except Exception:
            prime_router = None
        if prime_router:
            parts["solver"] = SP.SolverExecutor(SP.SolverPolicy(journal_path=os.path.join(state_dir or "/root/nox/state", "solver_journal.jsonl")), prime_router)
    except Exception:
        pass
    try:
        import predictive_self as PS
        parts["predictive"] = PS.PredictiveSelf(os.path.join(state_dir or "/root/nox/state", "predictive_self.json"))
    except Exception:
        pass
    if os.environ.get("NOX_MIND_BRIDGE", "1") == "1" and (parts.get("solver") or parts.get("predictive")):
        try:
            import mind_bridge as MB
            parts["bridge"] = MB.build_bridge(parts, state_dir or "/root/nox/state")
        except Exception:
            pass
    return Organs(**parts)
