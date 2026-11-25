echo "C300: k4_probe_2"
S=/workspace/nox/web/site; cd $S
ls *.html | tr '\n' ' '; echo
for v in chrono-node sortablejs embla-carousel fuse.js tweakpane pixi-filters nosleep.js maplibre-gl earth kbar shoelace; do echo "== $v"; ls vendor/$v | head -8 | tr '\n' ' '; echo; done
echo "== atlas"; grep -oE 'class="[^"]+"' atlas.html | sort -u | tr '\n' ' ' | cut -c1-800; echo; sed -n 1,400p atlas.html | grep -E "atLayers|atHint|atInfo|atQ" | cut -c1-400
echo "== atlas js"; wc -c nox-atlas-s1.js; grep -nE "window\.|export|globe|Globe|maplibre|flyTo|rotate|pointOfView" nox-atlas-s1.js | cut -c1-220 | head -50
echo "== registry"; python3 -c "
import json;r=json.load(open('qa/registry.json'));print(type(r).__name__,len(r));print(json.dumps(r)[:1500])"
echo "== cmd"; grep -nE "register|window.NOXcmd|run\(" nox-cmd.js | cut -c1-200 | head -20
