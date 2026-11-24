cd /workspace/nox/web/site; ls *bak_w3_* nox-*-x.* 2>&1; ls qa/rework
python3 - <<'P'
import json
d=json.load(open('/workspace/nox/web/site/qa/audit.json'))
print(json.dumps(d,ensure_ascii=False)[:1800])
P
grep -c "nox-music-x" music.html
