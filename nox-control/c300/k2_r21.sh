echo "C300: k2_r21"
N=/workspace/nox
sed -n 144,215p $N/stewards/orch_registry.json | cut -c1-210
echo "--- refs to Instruct-2507"; grep -rIl "Qwen3-30B-A3B-Instruct-2507" $N/stewards $N/serve $N/agent/autotrain $N/ops/*.sh $N/ops/*.py $N/agent/nox_agents $N/brain/BRAIN/*.py $N/judges 2>/dev/null | grep -v -E "\.bak|\.log" | head
cat $N/state/k2_sha.txt 2>/dev/null; cat $N/state/k2_etag.txt | grep -o "[0-9a-f]\{64\}"
