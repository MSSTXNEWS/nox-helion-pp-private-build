echo "C300: w_b3"
N=/workspace/nox
sed -n '1,10p' $N/ops/web_chat_auth/Caddyfile | grep -v -i -E 'auth|hash|pass|token|secret|\$2' 
sed -n '36,48p' $N/ops/web_chat_auth/Caddyfile | grep -v -i -E 'hash|pass|token|secret|\$2'
grep -v -i -E 'pass|token|secret|key' /etc/supervisor/conf.d/nox_web_chat_auth.conf | head -20
echo --ui_state; python3 -c "import json;d=json.load(open('$N/state/ui_state.json'));print(type(d).__name__, list(d)[:15] if isinstance(d,dict) else len(d))"
python3 -c "import json;d=json.load(open('$N/state/agenda_check.json'));print(json.dumps(d,ensure_ascii=False)[:500])"
echo --probe; for u in / /web/ /web/index.html /api/status /api/nox-live; do echo -n "$u "; curl -s -m5 -L -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18091$u; done
curl -s -m5 http://127.0.0.1:8810/worms/self | head -c 300; echo
grep -rn "settings" $N/web/site/nox-u-settings*.js 2>/dev/null | head -3
grep -o "api/settings[^'\"]*" -r $N/web/site/*.js $N/web/site/*.html 2>/dev/null | sort | uniq -c | head -5
grep -o "api/nox/status[^'\"]*" -r $N/web/site/*.js 2>/dev/null | sort | uniq -c | head
grep -o "api/notifications[^'\"]*\|api/nox/activity[^'\"]*\|api/training/status[^'\"]*" -r $N/web/site/*.js $N/web/site/*.html 2>/dev/null | sort | uniq -c | head
