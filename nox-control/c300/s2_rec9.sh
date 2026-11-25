#!/bin/bash
S=/workspace/nox/web/site
ls $S/vendor/nox-x $S/vendor/nox-x/globe $S/vendor/nox-x/butterchurn 2>&1 | head -40
find $S/vendor/nox-x -maxdepth 3 \( -iname '*butterchurn*' -o -iname '*cobe*' -o -iname '*globe*' -o -iname '*milkdrop*' \) | head -20
grep -c . $S/photo.html; sed -n '/<body/,/<script/p' $S/photo.html | cut -c1-300 | head -30
grep -o 'src="[^"]*"\|href="[^"]*css[^"]*"' $S/photo.html | head -30
ls $S/vendor | tr '\n' ' '
