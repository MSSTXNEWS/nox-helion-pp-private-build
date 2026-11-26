echo "C300: w_d6"
S=/workspace/nox/web/site; V=$S/vendor/tabler-icons/icons/outline
ls $V | wc -l; ls $V | grep -E '^(wand|arrows-minimize|microphone|abc|spell|ab-|text-spellcheck|minimize|wand-off)' | head
grep -c 'nox-a11y-fix' $S/qa.html $S/tv.html
grep -o '<script[^>]*src="[^"]*"' $S/qa.html | cut -c1-120 | head -12
python3 - <<'P'
import json
d=json.load(open('/workspace/nox/agent/out/ui_sc/tv_1440_lh.json'))
for k,a in d['audits'].items():
    if a.get('score') is not None and a['score']<1 and k in [r['id'] for r in d['categories']['best-practices']['auditRefs']]: print('BP',k,a['score'],(a.get('displayValue') or '')[:80])
for k,a in d['audits'].items():
    if k=='errors-in-console':
        for i in a.get('details',{}).get('items',[])[:5]: print('CONSOLE',str(i)[:200])
P
