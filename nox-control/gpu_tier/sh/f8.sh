echo "== F8"
pgrep -f run_all_tests >/dev/null && echo running
grep -a "^FAIL" -A3 /root/nox/logs/v5_tests.log | cut -c1-170 | head -50
