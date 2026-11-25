cat > /tmp/s5_chain4.sh <<'C'
for p in finance atlas settings news index chat photo board cinema creative music tv studio consciousness organism soul selffeel; do
  [ -f /workspace/nox/web/site/$p.html ] || continue
  flock /tmp/qaa.lock nice -n 5 /workspace/nox/venv/bin/python /workspace/nox/qa_audit.py $p.html >> /tmp/s5_chain4.log 2>&1
  echo "DONE $p $(date +%H:%M)" >> /tmp/s5_chain4.log
done
echo CHAIN_DONE >> /tmp/s5_chain4.log
C
pgrep -f s5_chain4.sh >/dev/null && echo "OUT: already running" || { : > /tmp/s5_chain4.log; setsid nohup bash /tmp/s5_chain4.sh >/dev/null 2>&1 < /dev/null & echo "OUT: chain4 started"; }
