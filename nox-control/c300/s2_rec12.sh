#!/bin/bash
S=/workspace/nox/web/site
ls $S/vendor | grep -i "shaka\|vidstack\|fabric\|transformers\|podcast\|whisper\|hls\|three\|planets\|cobe\|konva\|pdf\|page-flip\|turn" | tr '\n' ' '; echo
for f in tv creative editor; do echo "=== $f.html $(wc -c <$S/$f.html)"; sed -n '/<body/,$p' $S/$f.html | grep -v '^<script src="./nox-\|nox-pwa\|nox-ninja' | cut -c1-260 | head -28; done
grep -o '<script[^>]*src="[^"]*"' $S/creative.html $S/editor.html | grep -v "nox-nav\|nox-dock\|nox-ninja\|minichat\|pwa\|nox-pult\|nox-sun\|nox-state\|nox-cmd\|nox-actions\|cast-btn\|radial\|nox-live\|gesture\|worlds\|theme" | cut -c1-140
wc -c $S/nox-tv*.js $S/nox-creative*.js $S/nox-editor*.js 2>&1 | head
