"""Decision Context: persistent learning from owner corrections. A correction becomes a rule
(trigger keywords -> preferred behaviour), stored bi-temporally (newer corrections supersede older ones on the
same trigger), and is injected into future prompts when triggered. Also records decision traces."""
import re
from .bitemporal import BiTemporalStore

def _kw(s, n=6):
    return sorted({t for t in re.findall(r"\w+", s.lower()) if len(t) > 3})[:n]

class DecisionContext:
    def __init__(self, store: BiTemporalStore):
        self.s = store

    def learn_correction(self, persona_id, context_text, wrong, right, source="owner"):
        trig = " ".join(_kw(context_text)) or "general"
        tid = self.s.trace("correction", {"context": context_text, "wrong": wrong, "right": right})
        return self.s.assert_fact(persona_id, "rule:" + trig, "prefer", f"НЕ: {wrong} | ДА: {right}", source=source,
                                  trace_id=tid, importance=0.9, reason="owner_correction")

    def applicable(self, persona_id, user_text, k=3):
        words = set(re.findall(r"\w+", user_text.lower()))
        out = []
        for r in self.s._rows("SELECT * FROM fact WHERE persona_id=? AND predicate='prefer' AND expired_at IS NULL", (persona_id,)):
            trig = set(r["subject"][5:].split())
            ov = len(trig & words)
            if ov:
                out.append((ov, r))
        return [r for _, r in sorted(out, key=lambda x: (-x[0], -x[1]["created_at"]))][:k]

    def prompt_block(self, persona_id, user_text):
        rules = self.applicable(persona_id, user_text)
        if not rules:
            return ""
        return "Правила из прошлых исправлений владельца:\n" + "\n".join(f"- {r['object']}" for r in rules)

    def record_decision(self, kind, inputs, choice, rationale):
        return self.s.trace("decision:" + kind, {"inputs": inputs, "choice": choice, "rationale": rationale})
