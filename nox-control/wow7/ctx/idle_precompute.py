"""idle_precompute: «думать заранее» (sleep-time compute) - в простое готовит выжимки, карточку темы, прогрев KV, кандидаты в знания.

Правила: (1) не мешать владельцу: работает только если с его последнего сообщения прошло idle_after секунд, и между задачами
проверяет should_stop(); (2) LLM-работа идёт на БЫСТРОЙ модели (:8083), главную GLM не занимает; (3) прогрев KV (warm) только
после смены префикса (epoch), т.к. prefill на CPU-MoE дорог; (4) знания не пишутся в S03 напрямую - только JSONL-кандидаты
с якорями для консолидации (MEM-06).
"""
import argparse
import json
import os
import sys
import time

from ctxcommon import kv_warm_http, http_llm, LlamaTokenizer, sha256
from context_manager import ContextManager, TurnStore, Budgets
from summarizer import Summarizer


class IdleWorker:
    def __init__(self, cm, summarizer, warm=None, knowledge_path=None, clock=time.time, idle_after=45.0, card_every=4):
        self.cm, self.sm, self.warm = cm, summarizer, warm
        self.knowledge_path, self.clock = knowledge_path, clock
        self.idle_after, self.card_every = idle_after, card_every
        self.last_activity = clock()
        self.warmed = None
        self.log = []

    def touch(self, now=None):
        """Вызывать при каждом сообщении владельца."""
        self.last_activity = now if now is not None else self.clock()

    def _stop(self, should_stop):
        return bool(should_stop and should_stop())

    def tick(self, now=None, should_stop=None, sleep=False):
        now = now if now is not None else self.clock()
        if now - self.last_activity < self.idle_after:
            return {"state": "busy", "actions": [], "errors": []}
        acts, errs = [], []
        jobs = [("compact", self._compact), ("topic_card", self._card), ("warm", self._warm)]
        if sleep:
            jobs.append(("export_knowledge", self._export))
        for name, fn in jobs:
            if self._stop(should_stop):
                acts.append("stopped_before:" + name)
                break
            try:
                r = fn()
                if r:
                    acts.append(name if r is True else "%s:%s" % (name, r))
            except Exception as ex:
                errs.append("%s: %s" % (name, ex))
        return {"state": "idle", "actions": acts, "errors": errs}

    def _compact(self):
        if self.cm.l1_tokens() <= self.cm.b.l1_idle and self.cm.l2_tokens() <= self.cm.b.l2_max:
            return False
        made = self.cm.compact("llm", floor=self.cm.b.l1_low)
        if not made:
            self.cm.merge_if_needed("llm")
            self.cm.save()
        return "+%d сегм." % len(made) if made else False

    def _card(self):
        l1 = self.cm.l1_turns()
        last = l1[-1]["id"] if l1 else None
        if len(l1) < 4 or last is None:
            return False
        card = self.cm.topic_card
        if card and card.get("at_turn") and TurnStore.num(last) - TurnStore.num(card["at_turn"]) < self.card_every:
            return False
        seg_text = "\n".join(s["text"] for s in self.cm.segments if not s["paged"])
        new = self.sm.topic_card(l1, seg_text)
        if not new:
            return False
        new["at_turn"] = last
        self.cm.topic_card = new
        self.cm.save()
        return True

    def _warm(self):
        if self.warm is None:
            return False
        msgs = [{"role": "system", "content": self.cm.soul}] + self.cm.history_messages()
        key = sha256(json.dumps(msgs, ensure_ascii=False, sort_keys=True))
        if key == self.warmed:
            return False
        self.warm(msgs)
        self.warmed = key
        return True

    def _export(self):
        if not self.knowledge_path:
            return False
        done = set()
        if os.path.exists(self.knowledge_path):
            with open(self.knowledge_path, encoding="utf-8") as f:
                for line in f:
                    try:
                        done.add(json.loads(line)["source_id"])
                    except Exception:
                        pass
        n = 0
        with open(self.knowledge_path, "a", encoding="utf-8") as f:
            for s in list(self.cm.segments) + list(self.cm.archive.values()):
                if s["id"] in done or s["id"].count("+") or s["id"] in {c for x in self.cm.segments for c in x.get("covers", [])}:
                    continue
                anchors = {"seg": s["id"], "turns": [s["first"], s["last"]], "s03": s.get("s03", [])[:6]}
                rec = {"source_id": s["id"], "kind": "episode_summary", "text": s["text"], "anchors": anchors,
                       "decisions": [x["text"] for x in s["facts"] if x["kind"] == "decision"],
                       "hard_facts": [x["text"] for x in s["facts"] if x["kind"] in ("number", "date", "id", "url")][:40],
                       "confidence": 0.5, "level": s["level"], "created": s["created"]}
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n += 1
        return "%d записей" % n if n else False


def main(argv=None):
    ap = argparse.ArgumentParser(description="CTX idle: сворачивание/карточка темы/прогрев KV в простое")
    ap.add_argument("--db", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--soul", required=True)
    ap.add_argument("--llm-url", default="http://127.0.0.1:8083")
    ap.add_argument("--warm-url", default="")
    ap.add_argument("--tok-url", default="")
    ap.add_argument("--knowledge", default="")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--sleep", action="store_true", help="ночной режим: экспорт кандидатов в знания")
    ap.add_argument("--idle-after", type=float, default=45.0)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    soul = open(a.soul, encoding="utf-8").read()
    tok = LlamaTokenizer(a.tok_url) if a.tok_url else None
    sm = Summarizer(http_llm(a.llm_url), token_counter=(tok.count_text if tok else None) or __import__("ctxcommon").estimate_tokens)
    cm = ContextManager(soul, TurnStore(a.db), sm, token_counter=tok, state_path=a.state)
    if a.dry_run:
        print(json.dumps({"l1": cm.l1_tokens(), "l2": cm.l2_tokens(), "segments": len(cm.segments), "idle_after": a.idle_after,
                          "would_compact": cm.l1_tokens() > cm.b.l1_idle}, ensure_ascii=False))
        return 0
    w = IdleWorker(cm, sm, warm=kv_warm_http(a.warm_url) if a.warm_url else None, knowledge_path=a.knowledge or None,
                   idle_after=a.idle_after)
    w.last_activity = time.time() - a.idle_after - 1
    while True:
        print(json.dumps(w.tick(sleep=a.sleep), ensure_ascii=False), flush=True)
        if a.once:
            return 0
        time.sleep(30)


if __name__ == "__main__":
    sys.exit(main())
