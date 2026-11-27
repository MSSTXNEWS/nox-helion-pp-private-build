export RUNNER_TRACKING_ID=""
echo "C300: tr_cad3"
CF=/workspace/nox/ops/web_chat_auth/Caddyfile; wc -l $CF
grep -n -E "^\s*(handle|route|@|reverse_proxy|rewrite|uri|redir|respond)|^[:a-z0-9\[]|memory" $CF | sed -E 's/(hash|token|secret|password|key)[^ ]* +[^ ]+/\1 REDACTED/Ig' | cut -c1-170 | head -80
echo "== nox_mem routes"; grep -n -E 'path ?(==|\.startswith|in)|"/[a-z_/]+"' /workspace/nox/svc/mem/nox_mem.py | cut -c1-160 | head -25
grep -rn "api/nox/memory" /workspace/nox/ops/*.py /workspace/nox/svc/*/*.py /workspace/nox/web/*.js 2>/dev/null | cut -c1-170 | head -6
echo END
