echo "C300: ch_bg1"
N=/workspace/nox; ls -l $N/state/mock_qa | grep chat_ch
[ -f /tmp/crit_ch.py ] && { pgrep -f crit_ch.py >/dev/null || setsid -f python3 /tmp/crit_ch.py > $N/state/ch_crit.out 2>&1 < /dev/null; echo crit_started; } || echo nocrit
echo "== audit log"; tail -c 1500 $N/state/ch_audit1.log; pgrep -af qa_audit | head -2
