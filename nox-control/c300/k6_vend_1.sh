echo "C300: k6_vend_1"
S=/workspace/nox/web/site; cd $S/vendor
for spec in animate.css hover.css magic.css @formkit/auto-animate; do
 n=$(basename $spec); rm -rf /tmp/k6v/$n; mkdir -p /tmp/k6v/$n; cd /tmp/k6v/$n
 meta=$(curl -fsSL "https://registry.npmjs.org/$spec/latest" 2>&1 | head -c 100000)
 URL=$(echo "$meta" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['dist']['tarball'],d['version'],d.get('license'))" 2>&1)
 echo "## $spec $URL"; T=${URL%% *}
 curl -fsSL "$T" | tar xz 2>&1 | head -3
 find package -type f | head -40 | xargs ls -la | awk '{print $5,$9}'
done
echo "## existing vendor"
cd $S/vendor; ls -d tinykeys fuse* gridstack echarts 3d-force-graph cytoscape reveal* tone* excalidraw* codemirror* blocknote* transformers* orama* wavesurfer* 2>&1 | head -30
echo "## pages"; ls $S/*.html | xargs -n1 basename | tr '\n' ' '; echo
echo "## k4 core"; head -c 2500 $S/nox-k4-core.js; echo; grep -o "K4\.[a-zA-Z]*=" $S/nox-k4-core.js | sort -u | tr '\n' ' '
echo "## nox-ds"; ls $S | grep -i "ds\|sl-\|shoelace" | head; ls $S/vendor | grep -i "shoelace\|ds" | head
echo "## k5 models"; ls -la $S/nox-k5-*; head -c 1800 $S/nox-k5-diff.js
