echo "C300: srv_k6"
cd /workspace/nox/agents
sqlite3 worms.sqlite "select src,count(*),max(datetime(ts,'unixepoch')) from finds group by src; select * from quota order by hour desc limit 6;" 2>&1 | head -20
tail -5 worms.err 2>&1
./venv/bin/python -c "import feedparser;print('feedparser',feedparser.__version__)" 2>&1 | tail -1
./venv/bin/python -c "import huggingface_hub;print('hf',huggingface_hub.__version__)" 2>&1 | tail -1
cat /workspace/nox/state/worms_quota.json 2>&1 | head -3
ls /workspace/nox/state | grep -i worms
ps -o pid,ppid,etime,cmd -p $(ss -ltnp | grep ":8810 " | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2) | cut -c1-150
grep -rn "8810" /etc/supervisor/conf.d/*.conf 2>/dev/null | head -3; ls /etc/supervisor/conf.d | head -20
