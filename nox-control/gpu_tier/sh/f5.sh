echo "== F5"
ls -l /root/nox/in_flash | awk '{print $5,$9}' | head; sha256sum /root/nox/in_flash/F.zip | cut -c1-64
cd /root/nox/v5/nox_wow
sed -n 1,200p DEPLOY/HANDOFF_V7.md | cut -c1-230 | head -60
cat COMMON/run_all_tests.sh | head -20
