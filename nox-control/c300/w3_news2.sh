cd /workspace/nox/web/site
curl -s -m 8 127.0.0.1:8091/svc/freshrss/ | head -c 500; echo; echo ---
curl -s -m 8 -i "127.0.0.1:8091/svc/freshrss/i/?c=feed&a=list" | head -5
curl -s -m 8 127.0.0.1:8091/svc/freshrss/api/ | head -c 300; echo
grep -c "events.html" nav.json; grep -o '"file": "[a-z-]*.html"' nav.json | wc -l
ls /workspace/nox/ | grep -i fresh; ls /workspace | head -30; grep -il freshrss /workspace/nox/secrets.env 2>/dev/null | head -1
