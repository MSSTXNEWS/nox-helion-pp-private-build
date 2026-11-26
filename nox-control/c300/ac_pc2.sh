echo "C300: ac_pc2"
sed -n 128,165p /workspace/nox/brain/SEED/seed_core.py | cut -c1-200
grep -rn "build_messages_cached\|cache_prompt\|cache-reuse\|cache_reuse" /workspace/nox --include=*.py --include=*.sh -s 2>/dev/null | grep -v "/venv\|vendor\|staged\|\.bak\|jl_venv" | head -10 | cut -c1-200
P=$(pgrep -f "port 8104"|head -1); tr '\0' '\n' </proc/$P/cmdline | tail -12 | tr '\n' ' '; echo
cat /workspace/nox/tmp/ab/res.txt
