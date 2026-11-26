echo "C300: k_th9"
grep -n "cp \|rsync\|tar \|site" /workspace/nox/web/pkg/server/run_web.sh | head -20
ls -la /workspace/nox/web/pkg/ | head; find /workspace/nox/web/pkg -name nox-theme.js -printf "%s %TY-%Tm-%Td_%TH:%TM %p\n" 2>/dev/null | head
E=$(ls /workspace/nox/agent/*/bundles/th_graphite/ensure.sh /workspace/nox/agent/out/th_graphite/ensure.sh /workspace/nox/bundles/th_graphite/ensure.sh 2>/dev/null | head -1); echo "ensure=$E"
find /workspace/nox -maxdepth 5 -path '*th_graphite/ensure.sh' 2>/dev/null | head -3
