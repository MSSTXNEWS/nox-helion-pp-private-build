echo "C300: w_c1"
cd /workspace/nox/web/site
echo "=== ui activity"; grep -o ".\{0,300\}activity.\{0,500\}" nox-ui.js | grep -v sourceTtl | head -6 | cut -c1-800
echo "=== workspace notif"; grep -n -o ".\{0,200\}api/notifications.\{0,900\}" workspace.js | head -2 | cut -c1-1200
echo "=== workspace settings"; grep -n -o ".\{0,300\}api/settings.\{0,700\}" workspace.js | head -4 | cut -c1-1100
echo "=== telemetry training"; grep -n -o "function training.\{0,900\}\|const t=.\{0,200\}\|t\.\(status\|verdict\|best\|round\)[a-z_.]*" nox-telemetry.js | head -12 | cut -c1-500
grep -n -o "\bfunction system.\{0,1200\}" nox-telemetry.js | head -1 | cut -c1-1500
