echo "C300: ch_ver2"
N=/workspace/nox; P=$N/svc/pipeline
grep -c "def verified" $P/pipeline_svc.py; ls -l $P/pipeline_svc.py.bak_ch_ver 2>&1 | cut -c1-80
timeout 5 curl -s -m4 localhost:18217/health; echo; pgrep -af pipeline_svc | head -3; uptime
cat $N/state/ch_q10b.out 2>&1 | cut -c1-160; pgrep -af "q10|qa_audit" | cut -c1-100 | head
