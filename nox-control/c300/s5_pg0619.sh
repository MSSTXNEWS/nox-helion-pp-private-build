echo "OUT: probe=$(grep -c S5PROBE /workspace/nox/qa_audit.py) vend=$(grep -c S5VENDOR /workspace/nox/qa_audit.py)"
grep -a " WOW " /tmp/s5_chain.log | cut -c1-40 | sed 's/^/OUT: /'; tail -c 80 /tmp/s5_chain.log | sed 's/^/OUT: /'
