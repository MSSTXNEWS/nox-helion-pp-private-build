S=/workspace/nox/web/site; W=/workspace/nox/web/pkg/server/web_server.py
wc -c $S/nox-s2-creative.js; head -c 2500 $S/nox-s2-creative.js; echo; echo ==== fabric usage; grep -c fabric $S/nox-s2-creative.js
echo ==== vendors; ls $S/vendor | grep -iE "iro|pickr|freehand|filerobot|fabric|shoelace|potrace|imagetracer|svg|color|opentype|font|hotkeys|tinykeys|upng|pica|cropper|konva|paper|rough|tldraw|penpot|photopea|colorthief|fast-average|mathjs|jszip|filesaver|html2canvas|tippy|floating|interact|sortable|dnd|gridstack|mousetrap" | tr '\n' ' '
echo; sed -n 240,262p $W | cut -c1-260
grep -n "ALLOW_GLM_DIRECT\|PORT\|8080\|8081\|serve_forever\|ThreadingHTTPServer" $W | head | cut -c1-200
echo ==== env; ps aux | grep -E "web_server|llama|8104" | grep -v grep | cut -c1-250 | head
ss -ltnp 2>/dev/null | grep -E "8104|8200|8082|8500|:80[0-9][0-9]" | cut -c1-140
echo ==== img; curl -s -m 5 -X POST localhost:8080/img/generate -d '{}' | head -c 300
echo ==== k2qa; head -40 /tmp/k2_qa.py
echo ==== fixed; ls $S/qa/rework | head; ls $S/qa/rework | grep -i creative
