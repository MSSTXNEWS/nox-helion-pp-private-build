echo "== F7"
sleep 200
grep -c "^OK" /root/nox/logs/v5_tests.log; grep "^FAIL" /root/nox/logs/v5_tests.log | head; tail -n 2 /root/nox/logs/v5_tests.log | cut -c1-150; pgrep -f run_all_tests >/dev/null && echo running
