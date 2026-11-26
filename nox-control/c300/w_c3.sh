echo "C300: w_c3"
cd /workspace/nox/web/site
echo "=== ui"; sed -n '50,59p' nox-ui.js | cut -c1-700
echo "=== ws head"; sed -n '1,49p' workspace.js | cut -c1-300
echo "=== ws request"; grep -n 'function request\|const request' workspace.js | head -3; 
echo "=== upstream status shape"; curl -s -m5 http://127.0.0.1:8091/api/nox/status | python3 -c "import sys,json;d=json.load(sys.stdin);print(list(d)[:20])" 2>&1 | head -2
echo "=== other users of /api/training/status"; grep -n -o ".\{0,120\}'/api/training/status'.\{0,200\}" nox-p-training.js | head -2 | cut -c1-400
