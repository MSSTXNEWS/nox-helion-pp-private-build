#!/bin/bash
# S1: выложить community (волна 1) + обновлённый шлюз, прогнать тесты, прочитать результаты настройки GLM
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control
mkdir -p /root/nox/community /root/nox/glm53gw
for f in __init__ smart_turn chalie_router ada_monologue heartbeat_md disturb_check smart_memory riverse_ladder nell_reflex test_smart_turn test_chalie_router test_ada_monologue test_heartbeat_md test_disturb_check test_smart_memory test_riverse_ladder test_nell_reflex; do curl -fsSL $R/community/$f.py -o /root/nox/community/$f.py || echo "FAIL $f"; done
for f in gateway.py glm_profile.py persona_short_ru.txt; do curl -fsSL $R/glm53/$f -o /root/nox/glm53gw/$f; done
cd /root/nox/community && python3 -m unittest discover -p "test_*.py" 2>&1 | tail -3
echo "== tune.log"; tail -22 /root/nox/logs/tune.log
