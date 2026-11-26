echo "C300: srv_k5"
cd /workspace/nox/agents
sed -n '1,11p;24,31p;34,39p;50,90p' nox_worms.py | cut -c1-420
