echo "C300: srv_k8"
cd /workspace/nox/agents
sed -n '195,218p;233,246p' nox_worms.py | cut -c1-400
curl -s -m 15 https://huggingface.co/blog/feed.xml | head -c 700
