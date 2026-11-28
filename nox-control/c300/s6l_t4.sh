echo "K1: s6l_t4"
N=/workspace/nox
grep -rn "quiet_hours\|\"initiative\"\|'initiative'" $N/agent $N/mods $N/canon $N/web/pkg/server --include=*.py 2>/dev/null | cut -c1-210 | head -20
F=$(grep -rl "\"component\": \"initiative\"\|component=\"initiative\"\|'initiative'" $N/agent --include=*.py 2>/dev/null | head -2); echo "files: $F"
for f in $F; do echo "== $f lines=$(wc -l < $f) md5=$(md5sum < $f | cut -c1-8)"; grep -n "quiet\|initiative\|def " $f | cut -c1-200 | head -40; done
grep -n "outbox_owner" $N/web/pkg/server/liska_feedback.py | cut -c1-200 | head -8
echo "## passport prefix in chat_core"; grep -n "passport\|_pp_\|def _prefix\|self_now" $N/web/pkg/server/chat_core.py | cut -c1-180 | head -30
echo END
