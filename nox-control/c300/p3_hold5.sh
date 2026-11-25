N=/workspace/nox
echo "hold age now $(( $(date +%s) - $(stat -c %Y $N/state/orch/chat_hold 2>/dev/null || echo 0) ))s exists=$(ls $N/state/orch/chat_hold 2>&1 | head -1)"
echo "== where 'cf' conv ids are generated"; grep -rIn -E "['\"]cf['\"]\s*\+|conversation_id.*['\"]cf|\bcf\\$\{|'cf'|\"cf\"" $N/web/site/*.js $N/web/site/*.html $N/*.py $N/ops/*.py $N/stewards/*.py $N/agent/nox_agents/*.py 2>/dev/null | grep -v -E "\.bak|vendor|min\.js" | cut -c1-200 | head -10
echo "== web_conv ids all (count by prefix)"; ls $N/state/web/web_conv | sed -E 's/[0-9]{6,}.*/N/' | sort | uniq -c | sort -rn | head
echo "== who posts those (QA/tests?) grep 'Столица Испании'"; grep -rIl "Столица Испании" $N --include=*.py --include=*.sh --include=*.js --include=*.json 2>/dev/null | grep -v -E "state/|backup|\.bak" | head -5
