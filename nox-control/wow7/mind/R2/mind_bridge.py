"""R2/mind_bridge.py: ЕДИНЫЙ стык ядра CORE с органами разума (M1 Решатель, M3 Предсказательное я, M5 Growth, EMO drives, CON workspace, ACT gap_map).

Ядро (BRAIN/organs.py) делегирует сюда observe_turn/observe_late. Поток данных одного хода:
  исход (Совесть/STOP/поправка/латентность) -> награда -> solver.observe          [владелец награды: ядро, правила и Создатель; судья <= 50% веса]
                                            -> predictive.observe -> workspace (pe:*)   [внимание]
                                            -> CuriosityHub('pe:<ctx>') -> drives (очередь к EMO, раз в час)
                                            -> GrowthInbox.ingest('жизнь:<ctx>', награда, 'rule') -> growth.session() (единственный писатель growth.json)
Ходы бенчмарка (eval=True) не учат никого. Каждый ход обрабатывается не более одного раза (дедуп по turn_id).
"""
import os
import sys
import time
from collections import OrderedDict

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
for _d in (_HERE, os.path.join(_ROOT, "COMMON"), os.path.join(_ROOT, "MIND", "M1_ARCH"), os.path.join(_ROOT, "MIND", "M3_CONSCIOUS"), os.path.join(_ROOT, "MIND", "M5_GROWTH")):
    if os.path.isdir(_d) and _d not in sys.path:
        sys.path.append(_d)
import curiosity as CU

AREA = {"chat": "жизнь:диалог", "question": "жизнь:вопросы", "task": "жизнь:задачи"}
JUDGE_CAP = 0.5            # судья 4-9B не может весить в награде больше половины: остальное - правила/Создатель (защита от «угождения самому себе»)

try:
    from solver_policy import Outcome, reward_from_outcome
except ImportError:                                   # автономный запуск без M1
    Outcome = None
    reward_from_outcome = None


def _make_outcome(d):
    if Outcome is None:
        from types import SimpleNamespace
        return SimpleNamespace(**d)
    ok = set(Outcome.__dataclass_fields__)
    return Outcome(**{k: v for k, v in d.items() if k in ok})


class MindBridge:
    def __init__(self, solver=None, predictive=None, workspace=None, hub=None, inbox=None, judge=None, clock=time.time):
        self.solver, self.ps, self.ws, self.hub, self.inbox, self.judge, self.clock = solver, predictive, workspace, hub, inbox, judge, clock
        self._done = OrderedDict()
        self._ctx = OrderedDict()
        self.m = {"turns": 0, "skipped_eval": 0, "duplicates": 0, "late": 0, "feedback": 0, "errors": 0}

    # ---------- награда
    def blend_judge(self, oc, turn_id, info):
        if self.judge is None:
            return oc
        try:
            j = self.judge(turn_id, info)
        except Exception:
            return oc
        if j is None:
            return oc
        rule_q = 1.0 if oc.conscience_ok is True else 0.0 if oc.conscience_ok is False else 0.6
        oc.judge = (1 - JUDGE_CAP) * rule_q + JUDGE_CAP * max(0.0, min(1.0, float(j)))
        return oc

    def _reward(self, oc, cost=0.0):
        return reward_from_outcome(oc, cost) if reward_from_outcome else (1.0 if oc.conscience_ok else 0.0)

    def _remember(self, turn_id, ctx):
        self._ctx[turn_id] = ctx
        while len(self._ctx) > 2000:
            self._ctx.popitem(last=False)

    def _area(self, ctx):
        return AREA.get(ctx, AREA["question"])

    def _surprise_to_hub(self, turn_id):
        if self.ps is None or self.hub is None:
            return None
        last = (getattr(self.ps, "s", None) or {}).get("last")
        if last and last.get("turn_id") == turn_id:
            self.hub.feed(last["ctx"], last["surprise"], "predictive")
            return last["surprise"]
        return None

    # ---------- после хода (Летописец)
    def on_turn(self, turn_id, info):
        out = {}
        if info.get("eval"):
            self.m["skipped_eval"] += 1
            return {"skipped": "eval"}
        if turn_id in self._done:
            self.m["duplicates"] += 1
            return {"skipped": "duplicate"}
        self._done[turn_id] = 1
        while len(self._done) > 4000:
            self._done.popitem(last=False)
        self.m["turns"] += 1
        ctx = info.get("ctx") or "question"
        self._remember(turn_id, ctx)
        oc = _make_outcome(dict(info["outcome"]))
        oc = self.blend_judge(oc, turn_id, info)
        reward = self._reward(oc)
        out["reward"] = round(reward, 4)
        if self.solver is not None:
            try:
                self.solver.observe(turn_id, oc)
                out["solver"] = "observed"
            except Exception as e:
                self.m["errors"] += 1
                out["solver"] = "error: %s" % e
        if self.ps is not None:
            try:
                self.ps.observe(turn_id, outcome=info["success"], latency_s=info["latency_s"])
                out["predictive"] = "observed"
                if self.ws is not None:
                    out["workspace_posts"] = self.ps.post_to_workspace(self.ws)
            except Exception as e:
                self.m["errors"] += 1
                out["predictive"] = "error: %s" % e
        if self.inbox is not None:
            try:
                self.inbox.post_ingest(self._area(ctx), reward, "rule", ref=turn_id)
                out["growth"] = "queued"
            except Exception as e:
                self.m["errors"] += 1
                out["growth"] = "error: %s" % e
        if self.hub is not None:
            self.hub.flush(self.clock())              # раз в период: удивление ходов -> drives (очередь к EMO)
        return out

    # ---------- реакция Создателя в следующей реплике
    def on_late(self, prev_turn_id, reaction, corrected):
        out = {}
        self.m["late"] += 1
        ctx = self._ctx.get(prev_turn_id, "question")
        if self.solver is not None and corrected:
            try:
                self.solver.observe_late(prev_turn_id, _make_outcome({"corrected_next": True}))
                out["solver"] = "observe_late"
            except Exception as e:
                self.m["errors"] += 1
                out["solver"] = "error: %s" % e
        if self.ps is not None:
            try:
                self.ps.observe(prev_turn_id, reaction=reaction, final=True)
                out["predictive"] = "closed"
                if self.ws is not None:
                    self.ps.post_to_workspace(self.ws)
                s = self._surprise_to_hub(prev_turn_id)
                if s is not None:
                    out["surprise"] = s
            except Exception as e:
                self.m["errors"] += 1
                out["predictive"] = "error: %s" % e
        lab = (reaction or {}).get("label")
        if self.inbox is not None and (corrected or lab in ("approve", "frustrated")):
            score = 1.0 if lab == "approve" and not corrected else 0.0
            try:
                self.inbox.post_ingest(self._area(ctx), score, "creator", ref=prev_turn_id)
                out["growth"] = "queued_creator"
            except Exception:
                self.m["errors"] += 1
        return out

    # ---------- явная оценка 👍/👎 (v=+1/-1) - сильнейший сигнал
    def on_feedback(self, turn_id, v):
        self.m["feedback"] += 1
        ctx = self._ctx.get(turn_id, "question")
        out = {}
        if self.solver is not None:
            try:
                self.solver.observe_late(turn_id, _make_outcome({"creator_feedback": 1 if v > 0 else -1}))
                out["solver"] = "observe_late"
            except Exception as e:
                out["solver"] = "error: %s" % e
        if self.inbox is not None:
            self.inbox.post_ingest(self._area(ctx), 1.0 if v > 0 else 0.0, "creator", ref=turn_id)
            out["growth"] = "queued_creator"
        return out

    # ---------- закрытие пробела: ОДНА точка входа для ACT (gap_map.resolve + урок в Growth)
    def resolve_gap(self, gapmap, gid, evidence, area=None):
        res = gapmap.resolve(gid, evidence)
        if res.get("ok") and self.inbox is not None:
            g = gapmap.data["gaps"][gid]
            good = [e for e in evidence if e.get("quote") and gapmap._host_ok(e.get("url")) and not e.get("quarantined")]
            if good:
                self.inbox.post_lesson(area or ("пробел:" + g.get("topic", "общее")), g["question"], good[0]["quote"], good[0].get("url", ""))
                res = dict(res, lesson="queued")
        return res

    # ---------- периодически (планировщик): поток любопытства и внимание
    def tick(self, now=None, force=False):
        out = {"curiosity": self.hub.flush(now, force) if self.hub else []}
        if self.ps is not None and self.ws is not None:
            try:
                out["workspace_posts"] = self.ps.post_to_workspace(self.ws)
            except Exception:
                self.m["errors"] += 1
        return out

    def status(self):
        st = dict(self.m)
        if self.hub:
            st["curiosity_ledger"] = dict(self.hub.ledger)
        if self.inbox:
            st["growth_inbox_pending"] = self.inbox.pending()
        return st


def build_bridge(parts, state_dir):
    """Собрать мост из органов ядра (organs.build_default). Очереди лежат в state_dir; drives.json и growth.json мост НЕ пишет."""
    os.makedirs(state_dir, exist_ok=True)
    drives = CU.FeedDrives(os.path.join(state_dir, "drives.json"), os.path.join(state_dir, "drives_feed.jsonl"))
    hub = CU.CuriosityHub(drives.observe)
    inbox = CU.GrowthInbox(os.path.join(state_dir, "growth_inbox.jsonl"))
    return MindBridge(parts.get("solver"), parts.get("predictive"), parts.get("workspace"), hub, inbox)
