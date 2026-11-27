echo "K1: v1_02m"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
curl -sfL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/rv_turn.sh?cb=$(date +%s)" -o /tmp/rv_turn_v102.sh && bash /tmp/rv_turn_v102.sh | grep -E "^(MEM|ADDR|JM|LOAD)" | cut -c1-90
echo "--- llm-side"; tail -9 $N/state/chat_fast.log
echo "--- recall"; tail -4 $N/state/s03_recall.log
echo "--- pipe"; tail -4 $N/state/pipe_err.log 2>/dev/null | cut -c1-100
echo END
