echo "K1: s6l_t5"
F=/workspace/nox/agent/nox_agents/mind/p0.py; echo "md5=$(md5sum < $F | cut -c1-8)"
sed -n '125,170p' $F | cut -c1-240
grep -n "^import\|^from\|def now_msk\|def is_quiet" $F | head -12
echo END
