for k in selffeel growth soul consciousness organism; do echo "=== $k"; curl -s -m10 127.0.0.1:8091/brain/$k | head -c 1800; echo; done
echo ===stats; curl -s -m5 127.0.0.1:8091/glm/v1/nox/stats | python3 -c "import json,sys;d=json.load(sys.stdin);print(list(d.keys()));print(json.dumps(d.get('health'))[:900]);print({k:(str(v)[:200]) for k,v in d.items() if k!='health'})"
ls /workspace/nox/web/site/data 2>&1 | head
