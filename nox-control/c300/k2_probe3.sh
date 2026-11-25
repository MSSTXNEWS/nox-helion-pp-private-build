#!/bin/bash
S=/workspace/nox/web/site
echo "C300: k2_probe3"
for m in ogl html-to-image chrono-node tinykeys kbar tweakpane pixi-filters embla-carousel lrc-kit echarts sortablejs gridstack maplibre-gl; do echo "$m: $(ls $S/vendor/$m 2>&1 | head -4 | tr '\n' ' ')"; done
head -c 700 $S/qa/registry.json; echo
ls $S | grep -i -E 'chat-fx|k2' | tr '\n' ' '
head -c 1200 $S/nox-chat-fx.js
grep -o 'id="[a-zA-Z]*"' $S/chat.html | head -30 | tr '\n' ' '
exit 0
