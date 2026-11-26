# K1: окно рисования без ожидания 20 с (флаг state/draw_hold_s, по умолчанию 20; 0 = сразу). Откат: rm state/draw_hold_s или cp бэкапа.
p = "/workspace/nox/ops/draw/invoke_draw.py"; s = open(p, encoding="utf8").read()
a = "        if time.time() - os.path.getmtime(CHAT_HOLD) < 20:\n"; assert s.count(a) == 1
s = s.replace(a, "        if time.time() - os.path.getmtime(CHAT_HOLD) < _hold_s():\n")
b = "        return time.time() - os.path.getmtime(CHAT_HOLD) >= 3\n"; assert s.count(b) == 1
s = s.replace(b, "        return time.time() - os.path.getmtime(CHAT_HOLD) >= min(3, _hold_s())\n")
c = "def _window():\n"; assert s.count(c) == 1
s = s.replace(c, "def _hold_s():\n    try: return float(open('/workspace/nox/state/draw_hold_s').read().strip())\n    except Exception: return 20.0\n\n\n" + c)
open(p, "w", encoding="utf8").write(s)
