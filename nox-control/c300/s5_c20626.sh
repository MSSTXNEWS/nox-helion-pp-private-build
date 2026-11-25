if pgrep -f s5_chain.sh >/dev/null; then echo "OUT: chain running"; else
cat > /tmp/s5_chain2.sh <<'C'
for p in settings atlas photo chat index; do
  flock /tmp/qaa.lock nice -n 5 /workspace/nox/venv/bin/python /workspace/nox/qa_audit.py $p.html >> /tmp/s5_chain2.log 2>&1
done
echo CHAIN_DONE >> /tmp/s5_chain2.log
C
: > /tmp/s5_chain2.log; setsid nohup bash /tmp/s5_chain2.sh >/dev/null 2>&1 < /dev/null &
echo "OUT: chain2 started"; fi
tail -c 200 /tmp/s5_chain.log | sed 's/^/OUT: /'; ps aux | grep -c "qa_audit.py"
