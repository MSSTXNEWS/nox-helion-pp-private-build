"""V4.1 sampling presets and hot/cold hysteresis controller."""
import time

# reasoning_effort per README of ISTA-DASLab build: int 1..100 or low/high/max (=50/75/100); default high(75);
# all published benchmark numbers measured at 50. Temperatures are NOX defaults (estimates, to be tuned).
PRESETS = {
    "chat_fast":  {"reasoning": "off", "temperature": 0.7, "top_p": 0.95},
    "chat_live":  {"reasoning": "on", "reasoning_effort": "30", "temperature": 0.8, "top_p": 0.95},
    "default":    {"reasoning": "on", "reasoning_effort": "50", "temperature": 0.6, "top_p": 0.95},
    "coding":     {"reasoning": "on", "reasoning_effort": "75", "temperature": 0.2, "top_p": 0.9},
    "math_proof": {"reasoning": "on", "reasoning_effort": "100", "temperature": 0.0},
    "tool_agent": {"reasoning": "on", "reasoning_effort": "50", "temperature": 0.1},
    "creative":   {"reasoning": "off", "temperature": 1.0, "top_p": 0.98},
}

def request_body(preset, messages, **over):
    p = dict(PRESETS[preset]); p.update(over)
    body = {"messages": messages, "temperature": p.get("temperature", 0.6)}
    if "top_p" in p:
        body["top_p"] = p["top_p"]
    if p.get("reasoning") == "on":
        body["reasoning_effort"] = p["reasoning_effort"]  # string, per README
    else:
        body["chat_template_kwargs"] = {"thinking": False}
    return body

class Hysteresis:
    """Promote an item to HOT when its EWMA rate >= hi, demote to COLD when <= lo, with minimum dwell time."""
    def __init__(self, hi=0.6, lo=0.2, alpha=0.3, min_dwell_s=60.0, clock=time.monotonic):
        assert lo < hi
        self.hi, self.lo, self.alpha, self.dwell, self.clock = hi, lo, alpha, min_dwell_s, clock
        self.rate, self.state, self.since = {}, {}, {}

    def observe(self, key, used: bool):
        r = self.rate.get(key, 0.0); r += self.alpha * ((1.0 if used else 0.0) - r); self.rate[key] = r
        st = self.state.get(key, "cold"); now = self.clock()
        if now - self.since.get(key, -1e18) >= self.dwell:
            if st == "cold" and r >= self.hi:
                self.state[key], self.since[key] = "hot", now
            elif st == "hot" and r <= self.lo:
                self.state[key], self.since[key] = "cold", now
        return self.state.get(key, "cold")

    def hot_set(self):
        return sorted(k for k, s in self.state.items() if s == "hot")
