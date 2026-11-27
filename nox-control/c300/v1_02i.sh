echo "K1: v1_02i"
export RUNNER_TRACKING_ID=""
F=/workspace/nox/web/pkg/server/chat_core.py
grep -n "_via_fast(\|history =\|history=\|def _hist\|up_text =" $F | cut -c1-200 | head -20
echo END
