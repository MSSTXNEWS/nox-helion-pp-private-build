echo "C300: ui_g6"; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
curl -fsSL $R/ui_show.py -o /tmp/ui_show.py; date '+now %F %T'; python3 /tmp/ui_show.py; ls /workspace/nox/agent/out | grep ui_q; pgrep -af qa_audit | cut -c1-90
