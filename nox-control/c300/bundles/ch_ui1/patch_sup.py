import sys
p="/workspace/nox/agent/nox_agents/supervisor.py"; s=open(p,encoding="utf-8").read()
if "ch_golden_agent" in s: print("already"); sys.exit()
a='    ("chat-speed-watch", "chat_speed_watch", "первый токен чата", "body"),\n'
assert a in s
open(p,"w",encoding="utf-8").write(s.replace(a,a+'    ("ch-golden", "ch_golden_agent", "суточная проверка моделей советников golden-набором", "body"),\n',1)); print("patched")
