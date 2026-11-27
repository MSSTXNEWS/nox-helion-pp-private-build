echo "K1: l1_rc2"
W=/workspace/nox/web/pkg/server
sed -n 342,412p $W/chat_core.py | cut -c1-260
echo ======RUN_TURN; sed -n 469,640p $W/chat_core.py | cut -c1-260
echo == state; ls /workspace/nox/state | grep -i -E "chat_fast|ttft|disk|owner|STOP|lock" | head
tail -5 /workspace/nox/state/chat_fast.log
