"""Persona + Emotion facets, persona consistency across sessions, emotional validation, affective state (EASM-like)."""
import hashlib, json, re

EMOTIONS = ("joy", "sadness", "anger", "fear", "surprise", "disgust", "neutral")
# valence/arousal anchors per emotion label (Russell circumplex approx.)
VA = {"joy": (0.8, 0.5), "sadness": (-0.7, -0.3), "anger": (-0.7, 0.8), "fear": (-0.6, 0.7),
      "surprise": (0.1, 0.8), "disgust": (-0.6, 0.3), "neutral": (0.0, 0.0)}
VALIDATION_RU = {"sadness": "Понимаю, что это тяжело.", "anger": "Понимаю, это действительно раздражает.",
                 "fear": "Тревога здесь понятна.", "joy": "Рад это слышать!", "surprise": "Да, неожиданно.",
                 "disgust": "Понимаю, неприятно.", "neutral": ""}

class Persona:
    def __init__(self, persona_id, name, traits: dict, style: dict, invariants: list):
        self.persona_id, self.name, self.traits, self.style, self.invariants = persona_id, name, traits, style, invariants

    def card(self):
        return {"persona_id": self.persona_id, "name": self.name, "traits": self.traits, "style": self.style, "invariants": self.invariants}

    def card_sha(self):
        return hashlib.sha256(json.dumps(self.card(), sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def system_block(self, emotion_state=None):
        t = ", ".join(f"{k}={v}" for k, v in sorted(self.traits.items()))
        lines = [f"Ты — {self.name} (PersonaID {self.persona_id}, card {self.card_sha()[:12]}).", f"Черты: {t}.",
                 "Неизменно: " + "; ".join(self.invariants)]
        if emotion_state:
            lines.append(f"Текущее аффективное состояние собеседника: {emotion_state.label} (v={emotion_state.v:+.2f}, a={emotion_state.a:+.2f}).")
        return "\n".join(lines)

class EmotionState:
    """Exponentially smoothed valence/arousal per session (stateful affect)."""
    def __init__(self, alpha=0.4):
        self.alpha, self.v, self.a, self.label = alpha, 0.0, 0.0, "neutral"

    def update(self, label):
        label = label if label in VA else "neutral"
        tv, ta = VA[label]
        self.v += self.alpha * (tv - self.v); self.a += self.alpha * (ta - self.a); self.label = label
        return self

def validate_reply(reply, emotion_label, lang="ru"):
    """Prepend a short validation for negative/strong emotions if the reply doesn't already acknowledge it."""
    pre = VALIDATION_RU.get(emotion_label, "")
    if not pre or reply.strip().startswith(pre):
        return reply
    if emotion_label in ("sadness", "anger", "fear", "disgust", "joy"):
        return pre + " " + reply
    return reply

class ConsistencyChecker:
    """Cross-session persona consistency: pinned card hash + invariant checks (regex deny-list per invariant)."""
    def __init__(self, persona: Persona, deny_patterns: dict):
        self.p, self.deny, self.pinned = persona, {k: re.compile(v, re.I) for k, v in deny_patterns.items()}, persona.card_sha()

    def check(self, reply, current_persona: Persona = None):
        issues = []
        if current_persona is not None and current_persona.card_sha() != self.pinned:
            issues.append("persona_card_drift")
        for name, rx in self.deny.items():
            if rx.search(reply):
                issues.append("violates:" + name)
        return {"ok": not issues, "issues": issues}
