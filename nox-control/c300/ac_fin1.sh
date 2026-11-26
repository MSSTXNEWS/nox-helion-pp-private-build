echo "C300: ac_fin1"
D=/workspace/nox/tmp/ab; cut -c1-62 $D/res.txt; pkill -f ab2.sh; pkill -f "port 8190"; sleep 2; rm -rf $D; pgrep -f "port 8190" | wc -l; df -h /workspace | tail -1
tail -3 /workspace/nox/agent/autotrain/rounds/$(ls /workspace/nox/agent/autotrain/rounds | tail -1)/train.log | cut -c1-160; ls /workspace/nox/agent/autotrain/rounds | tail -1
