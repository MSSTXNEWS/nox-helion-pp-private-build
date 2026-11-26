echo "C300: srv_k148"
for p in 3631214 3627261 2436877; do renice 10 -p $p >/dev/null 2>&1; echo "pid $p nice $(ps -o ni= -p $p)"; done
W=$(readlink /proc/3627254/cwd); echo cwd $W; ls -t $W | head -12
for f in $(ls -t $W/*.log 2>/dev/null | head -2); do echo "== $f"; tail -n 12 $f | cut -c1-230; done
grep -n "8104\|8510\|8400\|UPSTREAM\|BODY\|LIVE_TURN\|timeout" $W/rte_server.py | head -25 | cut -c1-190
