echo "C300: w_b4"
cd /workspace/nox/web/site
for p in 'api/training/status' 'api/nox/activity' 'api/notifications' 'api/settings' 'api/nox/status'; do echo "=== $p"; grep -o ".\{0,200\}$p.\{0,420\}" nox-telemetry.js nox-ui.js workspace.js workspace-pages.js nox-p-training.js nox-connection-v13.js nox-services.js 2>/dev/null | grep -F "$p" | head -3 | cut -c1-700; done
echo === who loads on index; grep -o 'src="[^"]*\.js[^"]*"' index.html | tr '\n' ' ' | cut -c1-1500
