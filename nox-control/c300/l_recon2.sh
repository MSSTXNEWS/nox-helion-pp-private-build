echo S4RUN:l_recon2
cd /workspace/nox
sed -n 283,335p web/pkg/server/chat_core.py
echo "== first"; grep -ril "пишет первым\|write_first\|nox_first\|proactive" web/site/*.js web/site/*.html web/pkg/server/*.py 2>/dev/null | head
echo "== endpoints"; grep -o '"/api/[a-z_/]*"' web/pkg/server/*.py | sort -u | head -60
echo "== files"; ls web/site | grep -i "^nox-\(chat\|voice\|first\|mem\|greet\)" | grep -v bak | head -30
echo "== canon"; head -c 2500 state/NOX_LIFE_CANON_v3_2411.md
echo "== memory files"; ls state | grep -iv "LISKA\|bak\|\.md$" | head -50
echo "== last chat.fixed"; ls web/site/qa/rework | grep chat | head; tail -3 web/site/qa/rework/chat.fixed
