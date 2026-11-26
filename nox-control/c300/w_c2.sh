echo "C300: w_c2"
cd /workspace/nox/web/site
echo "=== ui"; grep -n 'observedKnown' nox-ui.js | head -3 | cut -c1-1400
echo "=== ws"; sed -n '50,110p' workspace.js | cut -c1-420
echo "=== tel training"; sed -n '393,425p' nox-telemetry.js | cut -c1-380
echo "=== tel system"; sed -n '473,500p' nox-telemetry.js | cut -c1-380
