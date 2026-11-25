echo "C300: k6_probe_1"
S=/workspace/nox/web/site; V=$S/vendor; cd $S
for d in tinykeys fuse.js gridstack echarts 3d-force-graph cytoscape reveal.js tone excalidraw-excalidraw codemirror blocknote transformers-js orama-orama; do echo "## $d: $(ls $V/$d | head -8 | tr '\n' ' ')"; done
ls -la $V/gridstack/* 2>/dev/null | awk '{print $5,$9}' | head -8
ls $V/shoelace | head -5
for p in system knowledge pdf music index memory studio assistant photo chat; do echo "## $p.html $(wc -c < $p.html 2>/dev/null)"; grep -o "<title>[^<]*" $p.html | head -1; grep -o 'id="[A-Za-z0-9_-]*"' $p.html | head -25 | tr '\n' ' '; echo; grep -o '<script[^>]*src="[^"]*"' $p.html | sed 's/<script[^>]*src=//' | tr '\n' ' ' | cut -c1-500; echo; done
echo "## NOXcmd"; grep -l "NOXcmd" *.js 2>/dev/null | head -5; grep -o "NOXcmd[^;]\{0,120\}" nox-*.js 2>/dev/null | head -5
echo "## K3.ask"; grep -o "ask:[^}]\{0,400\}" nox-k3-core.js | head -2
echo "## K4 rest"; grep -o "fab:function.*" nox-k4-core.js | head -c 900; echo; cat nox-k4-core.css | head -c 800
echo "## ds"; grep -o "\-\-sl-[a-z-]*" nox-ds-s1.css | sort -u | head -8; ls shoelace* 2>/dev/null | head -3; grep -o 'shoelace[^"]*' chat.html | head -3
echo "## k5 diff"; cat nox-k5-diff.js | head -c 3000
