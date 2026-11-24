S=/workspace/nox/web/site
echo "== report"
python3 - <<'P'
import json,collections
r=json.load(open('/workspace/nox/web/site/qa/report.json'))
print(type(r), list(r.keys())[:10] if isinstance(r,dict) else len(r))
s=json.dumps(r,ensure_ascii=False)
print(len(s)); print(s[:3500])
P
echo "== rework"; ls -la $S/qa/rework | head -40
echo "== canon files"; ls $S/nox-*.js | head -20
echo "== photo head"; grep -n "script\|link" $S/photo.html | head -20
echo "== 404 sources"; grep -rln "vendor/three\|vendor/postprocessing\|vendor/motion" $S --include=*.html --include=*.js 2>/dev/null | head; grep -rn "api/status\|music/health\|music/status" $S --include=*.html --include=*.js 2>/dev/null | head
ls /svc 2>/dev/null; ls $S/vendor 2>/dev/null | head
