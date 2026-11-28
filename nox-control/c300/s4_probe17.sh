N=/workspace/nox
echo "S4P17 $(date +%F_%H:%M)"
grep -n "morning_brief_v5\|def brief\|def seed_brief\|exam_brief" $N/mods/weekly_exam.py | cut -c1-240 | head
L=$(grep -n "def .*brief" $N/mods/weekly_exam.py | head -1 | cut -d: -f1); [ -n "$L" ] && sed -n "${L},$((L+22))p" $N/mods/weekly_exam.py | cut -c1-260
echo "## brief json shape"; python3 -I -c "
import json;d=json.load(open('$N/state/mind/morning_brief_v5.json'));print(list(d.keys()) if isinstance(d,dict) else type(d)); print({k:(v if not isinstance(v,(list,dict)) else type(v).__name__+str(len(v))) for k,v in d.items()})" 2>&1 | cut -c1-500
echo "## who writes morning_brief_v5 (gen)"; grep -rIl --include=*.py --include=*.sh "morning_brief_v5" $N 2>/dev/null | grep -v -E "venv|\.bak" | head -6
echo "## public chat reachable check"; H=$(curl -s -m4 http://127.0.0.1:20999/quicktunnel | sed -E 's/.*"hostname":"([^"]+)".*/\1/'); echo "public code=$(curl -s -m10 -o /dev/null -w '%{http_code} %{time_total}s' https://$H/)"
echo "## supervisor web turn programs"; supervisorctl status 2>/dev/null | grep -i -E "web|core|rte|gateway|chat" | cut -c1-90
