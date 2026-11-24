grep -v "^\s*at \|^\s*---" /workspace/nox/svc/data/jellyfin/log/log_20261124.log | grep -i "ftl\|err\|exception" | cut -c1-400 | tail -6
curl -s -m10 localhost:8096/svc/jellyfin/web/index.html | sed 's/<[^>]*>//g' | grep -i "error\|exception\|fail" | head -5 | cut -c1-300
