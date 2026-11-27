echo "K1: ln_t13"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
grep -rn "не отвечает, донор" $N --include=*.py -l 2>/dev/null | head -3
F=$(grep -rln "не отвечает, донор" $N --include=*.py 2>/dev/null | head -1); grep -n -B14 "не отвечает, донор" $F | cut -c1-190 | head -40
