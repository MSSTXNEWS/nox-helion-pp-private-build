#!/bin/bash
cd /root/nox && python3 - <<'P'
import sys, os; sys.path.insert(0,"/root/nox/repo/nox-control")
os.environ.update(NOX_MEMORY_DB="/root/nox/memory/s03.db", NOX_SOUL="0")
from qs6.memory_layer import MemoryLayer
m=MemoryLayer(); p=m.prepare("Как тебя ускорить? Что конкретно тормозит?","t1")
for f in p.get("facts") or []: print("-", str(f)[:160])
print(p.get("info"))
P
