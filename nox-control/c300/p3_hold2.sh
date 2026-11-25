N=/workspace/nox; wc -l $N/stewards/chat_guard.py; cat $N/stewards/chat_guard.py | cut -c1-210 | sed -n 1,140p
echo "== guard.log tail"; tail -n 12 $N/state/orch/guard.log | cut -c1-200
echo "== guard_state"; head -c 700 $N/state/orch/guard_state.json
