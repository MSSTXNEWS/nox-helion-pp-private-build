#!/bin/bash
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300; S=/workspace/nox/web/site
for f in nox-dock-wow.js photo.html tools.html; do curl -fsSL $R/$f -o $S/$f; done
n=0; for f in $S/*.html; do grep -q 'nox-shell-classic.js' $f && { sed -i '/<script src="nox-shell-classic.js" defer><\/script>/d' $f; n=$((n+1)); }; done; echo "classic shell removed from $n pages"
sed -i 's/textwrap.wrap(base64.b64encode(img).decode(), 4000)/textwrap.wrap(base64.b64encode(img).decode(), 900)/' /tmp/shot2.py
timeout 150 /workspace/nox/venv/bin/python /tmp/shot2.py 2>&1 | grep -v "^\s*$"
