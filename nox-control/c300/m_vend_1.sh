export PATH=/workspace/nox/tools/node/bin:$PATH
S=/workspace/nox/web/site; B=/workspace/nox/build_a; T=/tmp/m_vend; rm -rf $T; mkdir -p $T/ptr $T/ug; 
echo "OUT: df $(df -BG /workspace | tail -1 | awk '{print $4}') free"
cd $T/ptr && npm pack pulltorefreshjs --silent 2>&1 | tail -1 && tar xzf *.tgz && ls package/dist | head; 
mkdir -p $S/vendor/pulltorefresh $S/vendor/use-gesture
cp package/dist/index.umd.min.js $S/vendor/pulltorefresh/ 2>/dev/null; cp package/LICENSE* $S/vendor/pulltorefresh/ 2>/dev/null
grep -m1 '"version"' package/package.json
cd $B && npm ls @use-gesture/vanilla 2>/dev/null | head -3 || true
npm install --no-save --silent @use-gesture/vanilla 2>&1 | tail -2
echo "import {Gesture,DragGesture} from '@use-gesture/vanilla'; window.NOX_gesture={Gesture,DragGesture};" > $B/src/ug.js
node_modules/.bin/esbuild --bundle --minify --format=iife --log-level=warning src/ug.js --outfile=$S/vendor/use-gesture/use-gesture.iife.js
cp node_modules/@use-gesture/vanilla/LICENSE $S/vendor/use-gesture/ 2>/dev/null
grep -m1 '"version"' node_modules/@use-gesture/vanilla/package.json
du -sh $S/vendor/pulltorefresh $S/vendor/use-gesture $S/vendor/ios-haptics
ls $S/vendor/ios-haptics
echo "OUT: done"
