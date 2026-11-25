echo "C300: u_get6"
O=/workspace/nox/agent/out; cut -c1-330 $O/u_qac_prog.txt; echo ---; cut -c1-330 $O/u_qab_prog.txt | tail -4; pgrep -fa qa_audit | head -2; ls -la /workspace/nox/web/site/nox-tools.js | cut -c1-90; ls /workspace/nox/web/state 2>/dev/null | head
