echo "K1: v1_02j"
export RUNNER_TRACKING_ID=""
sed -n 28,75p /workspace/nox/svc/mem/nox_mem.py | cut -c1-230
sed -n 136,170p /workspace/nox/svc/mem/nox_mem.py | cut -c1-230
echo END
