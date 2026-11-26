echo "C300: srv_k142"
cd /workspace/nox; date -u +%T
sed -i 's/ev.append((tp,round(time.time()-t0,2)))/ev.append((tp,round(time.time()-t0,2),str({k:v for k,v in o.items() if k!="t"})[:110]))/' /tmp/k1probe.py 2>/dev/null
timeout 150 python3 /tmp/k1probe.py 8091 2>&1 | head -4 | cut -c1-900
echo "--- логи"; ls -t web/*.log state/logs/*.log logs/*.log 2>/dev/null | head -5; for f in $(ls -t web/*.log state/logs/*.log 2>/dev/null | head -3); do echo "== $f"; tail -n 6 $f | cut -c1-200; done
grep -n "\"stage\"" web/pkg/server/web_server.py | head -8 | cut -c1-180
