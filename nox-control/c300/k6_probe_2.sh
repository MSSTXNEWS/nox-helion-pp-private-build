echo "C300: k6_probe_2"
S=/workspace/nox/web/site; cd $S
echo "## LS keys"; grep -oh "nox\.[a-z0-9_.-]*\.v[0-9]" *.js 2>/dev/null | sort | uniq -c | sort -rn | head -30
echo "## api"; grep -oh "/api/[a-z_/-]*" nox-s4-memory.js nox-p-memory.js nox-photo.js nox-s2-photo.js nox-s2-music.js nox-p-system.js nox-k2-selask.js contacts.html calendar.html nox-notes*.js 2>/dev/null | sort | uniq -c | sort -rn | head -30
echo "## chat input"; grep -o '<[a-z-]* [^>]*id="input"[^>]*>' chat.html | head -2; grep -o '<form[^>]*id="form"[^>]*>' chat.html
echo "## music"; grep -o '<[a-z-]* [^>]*id="mAud"[^>]*>' music.html; grep -c . nox-s2-music.js; grep -o "mAud[^;]\{0,100\}" nox-s2-music.js | head -4
echo "## system tiles"; grep -o 'id="tiles"[^>]*>' system.html; grep -o "/api/[a-z_/-]*" nox-p-system.js | sort -u | head
echo "## knowledge api"; grep -o "fetch([^)]*)" knowledge.html nox-k3-studio.js | head -5
echo "## pdf"; grep -o "pdfjs[^\"' ]*" pdf.html nox-editor-s1.js | sort -u | head -4; ls vendor | grep -i "pdf" | head
echo "## data"; ls data | head -30
echo "## photo gallery"; grep -o "gTh[^;]\{0,160\}" nox-photo.js nox-s2-photo.js | head -3; ls vendor/transformers-js/dist | head -4; ls vendor/cytoscape/dist | head -3
echo "## k4 css classes"; grep -o "^\.k4-[a-z-]*" nox-k4-core.css | sort -u | tr '\n' ' '
echo "## tinykeys/fuse/tone export"; head -c 200 vendor/tinykeys/tinykeys.iife.js; echo; head -c 160 vendor/fuse.js/fuse.js.iife.js; echo; head -c 160 vendor/tone/tone.iife.js; echo; head -c 160 vendor/reveal.js/reveal.js.iife.js; echo; head -c 160 vendor/gridstack/gridstack-all.js;echo;ls -la vendor/tone/ vendor/reveal.js vendor/3d-force-graph | awk '{print $5,$9}'
