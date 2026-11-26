echo "C300: ch_tl1"
cb=$(date +%s); curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ch_ui1/tl.py?cb=$cb" -o /tmp/tl.py
for i in 1 2; do echo "-- run $i"; timeout 50 python3 /tmp/tl.py "Столица Бразилии?" qa-chtl$i$cb 2>&1 | head -30; done
grep -o '"race_s"[^,]*' /workspace/nox/state/persona.json /workspace/nox/persona.json 2>/dev/null | head -3
curl -s -m3 localhost:8200/running | cut -c1-200; echo
