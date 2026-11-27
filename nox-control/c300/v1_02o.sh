echo "K1: v1_02o"
export RUNNER_TRACKING_ID=""
F=/workspace/nox/web/pkg/server/chat_core.py
n=$(grep -n "^def make_ctx" $F | cut -d: -f1); sed -n "${n},$((n+22))p" $F | cut -c1-260
grep -n "up_text" $F | head -20 | cut -c1-200
echo END
