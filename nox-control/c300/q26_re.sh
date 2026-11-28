echo "K1: q26_re"
export RUNNER_TRACKING_ID=""
ls /tmp/q26_t.py >/dev/null 2>&1 || { echo NOTEST; echo END; exit 0; }
echo "md5 $(md5sum < /workspace/nox/web/pkg/server/chat_core.py | cut -c1-32)"
for i in 1 2; do python3 /tmp/q26_t.py 2>&1 | grep -E "^(DISTINCT|TOTAL|GREET_LATER|BAD|JF )" | cut -c1-160; done
echo "gate: $(tail -60 /workspace/nox/state/chat_gate.log | grep -oE "judge_err|judge_note kinds=[a-z0-9_:,]*" | sort | uniq -c | tr "\n" " ")"
echo END
