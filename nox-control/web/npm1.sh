#!/bin/bash
W=/root/nox/web; T=/tmp/npmw; rm -rf $T; mkdir -p $T; cd $T
npm init -y >/dev/null 2>&1
npm i --no-audit --no-fund --silent split.js dexie gridstack 2>&1 | tail -3
for p in split.js dexie gridstack; do d=node_modules/$p; echo "$p $(node -p "require('./$d/package.json').version") $(du -sh $d | cut -f1)"; done
mkdir -p $W/vendor/split.js $W/vendor/dexie $W/vendor/gridstack
cp node_modules/split.js/dist/split.min.js $W/vendor/split.js/ && echo split ok
cp node_modules/dexie/dist/dexie.min.js $W/vendor/dexie/ && echo dexie ok
cp node_modules/gridstack/dist/gridstack-all.js node_modules/gridstack/dist/gridstack.min.css $W/vendor/gridstack/ && echo gridstack ok
ls $W/vendor/vad-web/dist | head -12 | tr '\n' ' '; echo
ls $W/vendor/cytoscape/dist | grep min | tr '\n' ' '; ls $W/vendor/photoswipe | head -5 | tr '\n' ' '; echo
ls $W/pc/vendor/nox-extra | tr '\n' ' ' | cut -c1-400; echo
curl -s -o /dev/null -w "vendor via 8091: %{http_code} " http://127.0.0.1:8091/web/vendor/split.js/split.min.js; curl -s -o /dev/null -w "%{http_code} " http://127.0.0.1:8091/web/pc/vendor/nox-ux/Sortable.min.js; curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8091/web/vendor/vad-web/dist/silero_vad_v5.onnx
sed -n 95,103p /root/nox/web_server.py | cut -c1-200
df -h /root | tail -1
