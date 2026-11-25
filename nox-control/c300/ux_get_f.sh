echo "C300: ux_get_f"
O=/workspace/nox/agent/out; cat $O/ux_f_prog.txt 2>&1 | cut -c1-600; pgrep -fa "qa_audit|u_audit5|ux_fast" | cut -c1-90 | head -4
