echo "C300: ui_g3"; for i in 1 2 3 4 5 6; do grep -q FIN /workspace/nox/agent/out/ui_d1_prog.txt 2>/dev/null && break; sleep 15; done; cut -c1-1100 /workspace/nox/agent/out/ui_d1_prog.txt
