#!/bin/bash
cd /root/nox/web; B=$(ls -t nox-wow.js.b* | head -1); for f in $B nox-wow.js; do node -e "new Function(require('fs').readFileSync('$f','utf8'))" 2>&1 | sed -n '1,4p' | cut -c1-90 | tr '\n' '|'; echo " <- $f"; done
diff <(sed 's/GLM-5\.3-Flash/GLM-5.3/g' nox-wow.js) <(sed 's/GLM-5\.3-Flash/GLM-5.3/g' $B) >/dev/null && echo "only label changed"
