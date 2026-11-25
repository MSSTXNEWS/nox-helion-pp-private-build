echo "C300: u_rec7"
S=/workspace/nox/web/site; cd $S
echo "== img health"; curl -s -m 8 localhost:8091/img/health | head -c 900; echo
echo "== disabled src"; grep -rln "korea_img_disabled" /workspace/nox --include=*.py 2>/dev/null | head -3
f=$(grep -rln "korea_img_disabled" /workspace/nox --include=*.py 2>/dev/null | head -1); [ -n "$f" ] && grep -n "korea_img_disabled" $f | head -3 | cut -c1-260
python3 - <<'PYX'
import json
a=json.load(open('/workspace/nox/web/site/qa/audit.json',encoding='utf-8'))
d=a['index'];print('INDEX fails',json.dumps(d['fails'],ensure_ascii=False)[:2500]);print('fix',d.get('fix'))
print('raw',d['vision_raw'][:1200])
PYX
