echo "C300: w_d1"
S=/workspace/nox/web/site
grep -c 'sl-range' $S/nox-a11y-fix.js; wc -c $S/nox-a11y-fix.js; curl -s -o /dev/null -w '%{http_code} %{size_download}\n' http://127.0.0.1:8091/web/nox-a11y-fix.js
curl -s http://127.0.0.1:8091/web/settings.html | grep -o 'nox-a11y-fix[^"]*'
grep -c 'sl-range' /workspace/nox/web/pkg/webroot/nox-a11y-fix.js
