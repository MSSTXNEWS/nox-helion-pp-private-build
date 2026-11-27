echo "K1: rs_r5"
export RUNNER_TRACKING_ID=""
W=/workspace/nox; C=$W/web/pkg/server/chat_core.py
sed -n 640,775p $C | cut -c1-330
echo "--- client draft"; grep -o ".\{200\}advisors/draft.\{300\}" $W/web/site/ab1d/ab.js | head -2
echo "--- svc advisors"; grep -rn "advisors" $W/ops/web_chat_auth/Caddyfile | head -5
