echo "== F6"
ls -l /root/nox/in_flash | awk '{print $5,$9}' | head -5; sha256sum /root/nox/in_flash/F.zip 2>&1| cut -c1-64
cd /root/nox/v5/nox_wow
nohup setsid nice -n 10 bash COMMON/run_all_tests.sh --no-int > /root/nox/logs/v5_tests.log 2>&1 < /dev/null &
sleep 120; grep -c "^OK" /root/nox/logs/v5_tests.log; grep "^FAIL" /root/nox/logs/v5_tests.log | head; tail -n 2 /root/nox/logs/v5_tests.log | cut -c1-150
