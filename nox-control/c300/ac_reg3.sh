echo "C300: ac_reg3"
sed -n 40,70p /workspace/nox/ops/p3_axis_guard.py | cut -c1-200; grep -n "SPARE\s*=" /workspace/nox/ops/p3_axis_guard.py
cat /workspace/nox/ops/p3_cpuset_guard.sh | cut -c1-300
pgrep -af "p3_cpuset_guard|p3_axis_guard|dispatcher_worm|chat_guard" | cut -c1-140
