V=/workspace/nox/svc; cd $V
for v in v1.20.0 v1.15.2 v1.12.8 v1.10.3; do
  curl -fsSL -m100 https://github.com/meilisearch/meilisearch/releases/download/$v/meilisearch-linux-amd64 -o meili/meilisearch && chmod +x meili/meilisearch
  if ./meili/meilisearch --version 2>/dev/null | head -1; then echo OK $v; break; fi
done
nohup setsid bash $V/start_extra.sh >/dev/null 2>&1 &
sleep 30
tail -2 $V/logs/meili.log | cut -c1-160; cat $V/logs/index.log | tail -3 | cut -c1-200
curl -s -m5 "localhost:8091/search?q=календарь" | head -c 400; echo
