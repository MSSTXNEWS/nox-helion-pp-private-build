echo "C300: ch_dc23"
S=/workspace/nox/web/site/vendor/nox-liquid-glass
cat $S/NOX-INTEGRATION.txt; echo ==; tail -n +1 $S/liquid-glass.js | grep -n "export\|window\.\|function \|data-lg\|--lg-\|reduced\|ECO\|eco" | head -40 | cut -c1-220
echo == tail css; tail -c 500 $S/liquid-glass.css
