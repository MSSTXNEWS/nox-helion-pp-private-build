echo "C300: k_who1"
find /workspace/nox -name nox-theme.js -size -1k -printf "%s %TY-%Tm-%Td_%TH:%TM %p\n" 2>/dev/null | grep -v "/proc" | head -20
echo "--- logs mentioning restore/rsync after 02:05"
find /workspace/nox/agent/out /workspace/nox/state /tmp -maxdepth 2 -newermt "2026-11-26 02:05" -type f \( -name "*.log" -o -name "*.out" -o -name "*.sh" \) 2>/dev/null | xargs grep -l -E "nox-theme|webroot|cp -a|rsync|restore" 2>/dev/null | head -15
grep -rn "webroot\|cp -a\|rsync" /workspace/nox/web/pkg/server/run_web.sh | head
ps -eo pid,etimes,args | grep -E "[r]sync|[c]p -a|unify|restore" | head
