echo "K1: caddy_rs1"
export RUNNER_TRACKING_ID=""
CF=/workspace/nox/ops/web_chat_auth/Caddyfile
PID=$(pgrep -f "caddy.*web_chat_auth/Caddyfile" | head -1)
echo "pid_found=$([ -n "$PID" ] && echo yes || echo no)"
[ -n "$PID" ] || exit 1
BIN=$(readlink /proc/$PID/exe); CMD=$(tr '\0' ' ' < /proc/$PID/cmdline); CWD=$(readlink /proc/$PID/cwd)
$BIN validate --config $CF --adapter caddyfile >/dev/null 2>&1 && echo valid=yes || { echo valid=no; exit 1; }
SV=$(supervisorctl status 2>/dev/null | awk '{print $1}' | while read p; do supervisorctl pid $p 2>/dev/null | grep -qx "$PID" && echo $p; done | head -1)
if [ -n "$SV" ]; then echo "mode=supervisor"; supervisorctl restart $SV >/dev/null 2>&1
else
  echo "mode=direct"; ENVF=$(mktemp); tr '\0' '\n' < /proc/$PID/environ | grep -v '^RUNNER_TRACKING_ID=' > $ENVF; chmod 600 $ENVF
  kill $PID; for i in 1 2 3 4 5 6 7 8 9 10; do kill -0 $PID 2>/dev/null || break; sleep 0.3; done
  (cd $CWD && env -i $(cat $ENVF | sed 's/^/"/;s/$/"/' | tr '\n' ' ' | xargs -0 echo >/dev/null; true) true)
  (cd $CWD && set -a && . <(sed 's/^\([^=]*\)=\(.*\)$/\1='"'"'\2'"'"'/' $ENVF) && set +a && setsid -f $CMD </dev/null >>/workspace/nox/logs/caddy_web_chat.log 2>&1)
  rm -f $ENVF
fi
sleep 3
echo "new_pid=$([ -n "$(pgrep -f 'caddy.*web_chat_auth/Caddyfile')" ] && echo yes || echo no)"
for u in /web/chat-dc.html /api/nox/status /api/nox/memory/health /api/turn; do echo "$u $(curl -s -o /dev/null -m 8 -w %{http_code} http://127.0.0.1:18091$u)"; done
echo "gate $(curl -s -o /dev/null -m 8 -w %{http_code} -u owner:$(cat /workspace/nox/state/owner_gate/pass) http://127.0.0.1:18092/web/chat-dc.html)"
