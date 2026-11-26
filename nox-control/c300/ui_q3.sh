echo "C300: ui_q3"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
curl -fsSL $R/ui_show.py -o /tmp/ui_show.py; O=/workspace/nox/agent/out; date '+now %F %T'
setsid -f bash -c 'for p in system memory map knowledge widgets projects music news cinema mail calendar; do QA_FAST=1 flock /tmp/qaa.lock /workspace/nox/venv/bin/python /workspace/nox/qa_audit.py $p.html > '$O'/ui_q3_$p.out 2>&1; done' </dev/null >/dev/null 2>&1
python3 /tmp/ui_show.py
