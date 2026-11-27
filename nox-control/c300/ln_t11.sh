echo "K1: ln_t11"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
grep -n "def _u\|_USER\|USER\[" $N/svc/living/living_svc.py | head -12 | cut -c1-170
sed -n 205,240p $N/svc/living/living_svc.py | cut -c1-200
echo "== inner detail"; grep -m3 "не отвечает" $N/agent/out/inner_loop.log | cut -c1-260
for p in 8104 8105 8106 8141 8142 8144; do ss -ltn | grep -q ":$p " && echo "$p up" || echo "$p DOWN"; done
