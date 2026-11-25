F=/workspace/nox/web/pkg/server/chat_core.py
echo "== CC2"; sed -n 390,400p $F | cut -c1-260; echo ----; sed -n 443,452p $F | cut -c1-300
grep -n "^import\|^from" $F | head -12
