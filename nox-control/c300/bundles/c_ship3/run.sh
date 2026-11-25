N=/workspace/nox; S=$N/web/site; B=$N/svc/pipeline/ship3; O=$N/state/c_ship3.out; exec > $O 2>&1
cp -n $S/nox-chat-clean.js $S/nox-chat-clean.js.bak_c_ship3; cp $B/nox-chat-clean.js $B/nox-chat-clean.css $S/
sed -i 's#nox-chat-clean.css?v=[0-9]*#nox-chat-clean.css?v=3#;s#nox-chat-clean.js?v=[0-9]*#nox-chat-clean.js?v=3#' $S/chat.html; grep -c "clean.*v=3" $S/chat.html
echo "== 8793 coder3b?"; curl -s -m5 localhost:8793/v1/models | python3 -c "import sys,json;[print(m['id'],m.get('latency_ms')) for m in json.load(sys.stdin)['data'] if 'coder' in m['id']]"
grep -n "coder3b\|lcoder" -r $N/web/pkg/server/chat_core.py $N/svc/pipeline/*.py 2>/dev/null | head -3 | cut -c1-200
echo FINISHED
