echo "C300: srv_k4"
cd /workspace/nox/agents
wc -l nox_worms.py; grep -n "def \|huggingface\|api.github\|feedparser\|requests\.\|urlopen\|timeout\|except" nox_worms.py | head -90
