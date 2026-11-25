echo "C300: k6_probe_3"
S=/workspace/nox/web/site; V=$S/vendor; cd $S
ls -la $V/excalidraw-excalidraw $V/blocknote $V/codemirror $V/orama-orama $V/transformers-js/dist $V/gridstack | awk '{print $5,$9}' | grep -v "^ *$"
for f in excalidraw-excalidraw/excalidraw-excalidraw.iife.js blocknote/blocknote.iife.js codemirror/codemirror.iife.js orama-orama/orama-orama.iife.js; do echo "## $f"; head -c 300 $V/$f | tr '\n' ' '; echo; grep -o "NOX_[a-z_0-9]*" $V/$f | head -1; done
grep -o "React[A-Za-z.]*" $V/excalidraw-excalidraw/excalidraw-excalidraw.iife.js | sort | uniq -c | sort -rn | head -3
ls $V | grep -i "^react\|preact\|prosemirror\|tiptap"
echo "## index page"; grep -o '<main[^>]*>\|<section[^>]*id="[^"]*"' index.html | head; sed -n 1,400p index.html | grep -o 'id="[a-zA-Z]*"' | tr '\n' ' '
echo "## gallery json"; head -c 400 data/studio_gallery.json; echo; grep -o 'id="gTh"[^>]*>' photo.html; grep -o "<img[^>]*>" photo.html | head -2
echo "## memory data"; grep -o "fetch([^)]*)" nox-s4-memory.js nox-p-memory.js | head -6
grep -o "/api/[a-z_/?=-]*" nox-p-memory.js nox-s4-memory.js memory.html | sort -u | head
echo "## studio root"; grep -o "stRoot[^;]\{0,100\}" nox-s2-studio.js | head -2
echo "## assistant edCode"; grep -o '<[a-z-]* [^>]*id="edCode"[^>]*>' assistant.html
