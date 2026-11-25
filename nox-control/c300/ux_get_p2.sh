echo "C300: ux_get_p2"
O=/workspace/nox/agent/out; cat $O/ux_qa_prog.txt $O/ux_qa2_prog.txt 2>&1 | cut -c1-420; pgrep -fa "qa_audit|ux_aud" | cut -c1-100 | head -4
