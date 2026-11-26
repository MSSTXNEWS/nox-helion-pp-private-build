echo "C300: ch_swdep2"
S=/workspace/nox/web/site; cb=$(date +%s); R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ch_sw
mkdir -p /tmp/chsw; for f in sw.js patch_pwa.py; do curl -fsSL --retry 5 --retry-all-errors "$R/$f?cb=$cb" -o /tmp/chsw/$f && [ -s /tmp/chsw/$f ] || { echo FAIL $f; exit 0; }; done
grep -q "hadAny" /tmp/chsw/sw.js && grep -q "c.navigate(c.url).catch" /tmp/chsw/sw.js || { echo STALE; exit 0; }
cp $S/sw.js $S/sw.js.bak_ch_$cb; cp $S/nox-pwa.js $S/nox-pwa.js.bak_ch_$cb
cp /tmp/chsw/sw.js $S/sw.js; true
curl -s -m5 localhost:8091/web/sw.js | head -c 90; echo; curl -s -m5 localhost:8091/web/nox-pwa.js | grep -c CH-SW-RELOAD
echo "rollback: cp sw.js.bak_ch_$cb nox-pwa.js.bak_ch_$cb"
echo "== audit"; tail -c 600 /workspace/nox/state/ch_audit1.log; pgrep -af qa_audit | cut -c1-90 | head -3
python3 -I -c "
import json;d=json.load(open('/workspace/nox/web/site/qa/audit.json'))['chat'];print(d.get('ts'));[print('-',f['item'][:80],'|',str(f['detail'])[:200]) for f in d.get('fails',[])]" 2>&1 | head -8
