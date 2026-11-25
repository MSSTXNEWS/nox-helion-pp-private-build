echo "C300: ux_insp1"
Q=/workspace/nox/qa_audit.py; wc -l $Q; ls $Q.bak* 2>/dev/null | head -3
grep -n "median\|vision_runs\|QA_FAST\|max_tokens\|range(3)\|def vision\|def audit\|screenshot\|for vp\|\"mob\"" $Q | cut -c1-230
S=/workspace/nox/web/site
echo == textures; for f in assets/nox-approved/hdr/machine_shop_01_1k.hdr assets/nox-approved/metal/Metal012_1K-JPG_Color.jpg vendor/nox-planets/2k_moon.jpg vendor/nox-planets/nox-mars.jpg; do ls -la $S/$f 2>&1 | cut -c1-120; done
ls $S/vendor/nox-planets 2>&1 | head; ls $S/assets/nox-approved 2>&1 | head
grep -n "machine_shop\|Metal012\|2k_moon\|nox-mars" $S/about.html $S/integrations.html $S/nox-*.js 2>/dev/null | cut -c1-200 | head -8
echo == board; grep -n "EXCALIDRAW_ASSET_PATH\|excalidraw.production" $S/board.html | cut -c1-160; ls $S/vendor/nox-x/excalidraw/dist/ | head -5
echo == qa.html; grep -c 'id="app"' $S/qa.html
