#!/bin/bash
S=/workspace/nox/web/site
ls $S/vendor/planets/2k 2>&1 | head; ls $S/vendor/planets | head
ls $S/tv.html $S/creative.html $S/editor.html $S/design.html 2>&1
grep -o '"[a-z]*\.html"' $S/nav.json 2>/dev/null | sort -u | tr '\n' ' '
grep -o 'creative[^"]*\|editor[^"]*' $S/nav.json | sort -u | head
echo ==tv; sed -n '/<body/,/<script/p' $S/tv.html | cut -c1-300 | head -25; grep -o '<script[^>]*src="[^"]*"' $S/tv.html | cut -c1-90 | head -30
ls $S/vendor/nox-x/fx2 $S/vendor/nox-x/cropper | head; ls $S/vendor | tr '\n' ' '
ls /workspace/nox/web/site/vendor/ | grep -i "shaka\|vidstack\|fabric\|transformers\|podcast"
