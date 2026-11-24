cd /workspace/nox/web/site; touch qa/rework/cinema.fixed; cut -c1-500 nox-svc-embed.js; echo ====; sed -n '19,40p' music.html | cut -c1-1500
grep -n "dead\|мёртв" /workspace/nox/qa_audit.py | head -12
