#!/bin/bash
S=/workspace/nox/web/site
grep -n "NOXds\.\|empty\|skeleton\|unavailable" $S/nox-ds.js | head -30 | cut -c1-220
echo ---; grep -n "ds-empty\|ds-skel" $S/nox-ds.css | head -8 | cut -c1-200
echo ---; ls $S/vendor | grep -i "draw\|diagram"; ls $S/vendor/drawio 2>/dev/null | head; grep -n -i "drawio" /workspace/nox/c300_vendor_index.md 2>/dev/null | head -3
grep -n "s2_podcast" /workspace/nox/svc/start_extra.sh | cut -c1-80
