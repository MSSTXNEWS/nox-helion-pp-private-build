echo "C300: ux_get_p1"
O=/workspace/nox/agent/out; cat $O/ux_qa_prog.txt 2>&1 | cut -c1-400; pgrep -fa "qa_audit|u_audit5|ux_aud" | cut -c1-100 | head -4; cat $O/u_qab_prog.txt 2>&1 | cut -c1-300 | tail -4
