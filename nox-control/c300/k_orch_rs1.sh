echo "C300: k_orch_rs1"
PID=$(pgrep -f "stewards/nox_orch.py" | head -1); echo "old pid $PID"
[ -n "$PID" ] || exit 1
/workspace/nox/venv/bin/python -m py_compile /workspace/nox/stewards/nox_orch.py && echo "orch compiles" || exit 1
CWD=$(readlink /proc/$PID/cwd); tr '\0' '\n' < /proc/$PID/cmdline > /tmp/orch_cmd; tr '\0' '\n' < /proc/$PID/environ > /tmp/orch_env
PP=$(ps -o ppid= -p $PID | tr -d ' '); echo "parent $(ps -o cmd= -p $PP | cut -c1-80)"
cat > /workspace/nox/agent/out/k_orch_bg.sh <<BG
L=/workspace/nox/agent/out/k_orch_bg.log; echo "start \$(date)" > \$L
kill $PID; sleep 12
NEW=\$(pgrep -f "stewards/nox_orch.py" | head -1)
if [ -z "\$NEW" ]; then cd $CWD; mapfile -t C < /tmp/orch_cmd; env -i \$(grep -E '^(PATH|HOME|PYTHONPATH|NOX_[A-Z_]*|LANG)=' /tmp/orch_env | tr '\n' ' ') setsid -f "\${C[@]}" >> /workspace/nox/agent/out/nox_orch_restart.log 2>&1 < /dev/null; echo relaunched >> \$L; else echo "supervisor restarted \$NEW" >> \$L; fi
sleep 60
for p in 8141 8142 8143; do q=\$(ss -ltnp | grep ":\$p " | grep -o 'pid=[0-9]*' | cut -d= -f2 | head -1); echo "\$p pid=\$q state=\$(ps -o stat= -p \$q)" >> \$L; done
pgrep -af "stewards/nox_orch.py" | cut -c1-100 >> \$L
BG
setsid -f bash /workspace/nox/agent/out/k_orch_bg.sh > /dev/null 2>&1 < /dev/null
echo scheduled
