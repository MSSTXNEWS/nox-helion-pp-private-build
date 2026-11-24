echo "== proc"; ps -o pid,args -p 2623,2528 | cut -c1-250
P=$(readlink /proc/2623/cwd); echo cwd=$P; ls -la $P | head -30
echo "== cmdline"; tr '\0' ' ' </proc/2623/cmdline; echo
for f in $(ls $P/*.py 2>/dev/null | head -5); do echo "--- $f"; wc -l $f; done
echo "== c300_voice"; ls -R /workspace/nox/c300_voice | head -40; cat /workspace/nox/c300_voice/start.sh | head -30
echo "== textproc"; grep -rl "textproc" /workspace/nox --include=*.py 2>/dev/null | head -5
echo "== venvs"; ls /workspace/nox/tools/engines/venv /workspace/nox/tools/engines/bin | head; 
