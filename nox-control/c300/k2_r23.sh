echo "C300: k2_r23"
N=/workspace/nox
grep -nE "pause|PAUSE_D|\.off" $N/stewards/nox_orch.py | cut -c1-210 | head -20
sed -n 262,276p $N/stewards/nox_orch.py | cut -c1-200
ls $N/state/orch/ | head -30; ls $N/state/orch/pause 2>/dev/null
P=$(ss -ltnp | grep ':8143 ' | grep -o 'pid=[0-9]*' | cut -d= -f2); ps -o pid,stat,rss,etimes -p $P
