export RUNNER_TRACKING_ID=""
echo "C300: tr_cc1"
F=$(find /workspace/nox -maxdepth 4 -name chat_core.py -not -path "*/node_modules/*" 2>/dev/null | head -3); echo "$F"
F=$(echo "$F" | head -1); wc -l $F; ls -la $(dirname $F) | grep -i -E "chat|passport" | head
grep -n -E "^def |^class |^async def |_persona_prefix|img/generate|id_slot|PERSONA_PREFIX|passport|chat_fast|DEADLINE|deadline|TIMEOUT|timeout" $F | cut -c1-150 | head -90
find /workspace/nox -maxdepth 4 -name "passport*.json" 2>/dev/null | head -3
ls /workspace/nox/agent/out | grep -i chat_fast | head -2
echo END
