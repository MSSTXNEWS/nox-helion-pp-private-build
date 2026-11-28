N=/workspace/nox
echo "S4P19 $(date +%F_%H:%M)"
L=$(grep -n "chat_uptime_24h" $N/mods/weekly_exam.py | head -1 | cut -d: -f1); sed -n "$((L-3)),$((L+4))p" $N/mods/weekly_exam.py | cut -c1-220
python3 -I - <<'PY'
import sys; sys.path.insert(0,"/workspace/nox/mods")
import weekly_exam as W
v,f,why=W.p1(); print(sorted(v.keys()), f)
ud=W.jl(W.S+"/uptime_daily.json"); print(type(ud), W.S)
PY
