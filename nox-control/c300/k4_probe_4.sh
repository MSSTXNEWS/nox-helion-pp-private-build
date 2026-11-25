echo "C300: k4_probe_4"
S=/workspace/nox/web/site; cd $S
echo "== atlas 1-15"; sed -n 1,15p nox-atlas-s1.js | cut -c1-500
echo "== pcal"; sed -n 1,38p nox-p-calendar.js | cut -c1-330
echo "== globals"; for f in chrono-node/chrono-node.iife.js sortablejs/sortablejs.iife.js fuse.js/fuse.js.iife.js tweakpane/tweakpane.iife.js nosleep.js/nosleep.js.iife.js embla-carousel/embla-carousel.iife.js; do echo "$f: $(head -c 300 vendor/$f | tr '\n' ' ' | cut -c1-200) ... $(tail -c 200 vendor/$f | tr '\n' ' ')"; done
echo "== ds css vars"; grep -oE "\-\-(bg|fg|ac|mg|card|line|head)[a-z0-9-]*:[^;]+" nox-ds.css 2>/dev/null | head -12; ls *.css | head -30 | tr '\n' ' '
echo "== effects"; sed -n '/<body/,/<script/p' effects.html | cut -c1-260 | head -20
echo "== tasks sample"; grep -nE "nox.tasks.v1" nox-p-calendar.js nox-state.js 2>/dev/null | cut -c1-260 | head
