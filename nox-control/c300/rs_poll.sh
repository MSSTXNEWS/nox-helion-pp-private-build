echo "K1: rs_poll"
export RUNNER_TRACKING_ID=""
cat /workspace/nox/state/rs_t.log; tail -3 /workspace/nox/state/body_restart.log | cut -c1-200; cat /proc/loadavg
