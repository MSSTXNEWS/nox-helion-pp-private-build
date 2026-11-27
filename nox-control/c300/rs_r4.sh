echo "K1: rs_r4"
export RUNNER_TRACKING_ID=""
W=/workspace/nox; C=$W/web/pkg/server/chat_core.py
wc -l $C; grep -nE "deep|advis|18217|8793|backend|stage|\"fast\"|user_id" $C | cut -c1-210 | head -90
echo "--- advisors draft"; grep -rnE "advisors/draft" $W/web/pkg/server/*.py $W/ops/web_chat_auth/Caddyfile 2>/dev/null | cut -c1-200 | head; grep -rln "advisors/draft" $W/web/site/ab1d $W/web/site/*.html 2>/dev/null | head -3
ls $W/state/*.off | head -30
