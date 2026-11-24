S=/workspace/nox/web/site
mkdir -p $S/vendor/nox-x/reveal/fonts/source-sans-pro; [ -f $S/vendor/nox-x/reveal/fonts/source-sans-pro/source-sans-pro.css ] || echo "/* шрифт Source Sans Pro не входит в поставку; используется системный */" > $S/vendor/nox-x/reveal/fonts/source-sans-pro/source-sans-pro.css
sed -n 54,80p $S/nox-registry.js | cut -c1-420
echo ==about; grep -n "have\|exists\|probe\|head\|HEAD\|status" $S/nox-p-about.js | cut -c1-300 | head -12
ls -la --time-style=full-iso $S/qa/report.json; python3 -c "
import json;r=json.load(open('$S/qa/report.json'));print(r['ts'],r['bad'],r['total'])"
grep -n "sleep\|while\|cron" /workspace/nox/qa_audit_loop.sh | head -5; crontab -l 2>/dev/null | grep qa
