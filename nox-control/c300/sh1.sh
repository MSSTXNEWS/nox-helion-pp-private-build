#!/bin/bash
S=/workspace/nox/web/site
for f in $S/nox-shell.js $(find $S/lib /workspace/nox/web/pkg -name "nox-shell.js" 2>/dev/null | head -5); do echo "$f $(wc -c <$f) export=$(grep -c '^export' $f) $(grep -o '^export [a-z]* [A-Za-z]*' $f | head -5 | tr '\n' ' ') mtime=$(stat -c %y $f | cut -c1-16)"; done
grep -ln "from './nox-shell.js'" $S/*.js | head; grep -h "from './nox-shell.js'" $S/*.js | sort | uniq -c | head
ls -la $S/nox-shell.js* | head
grep -c "nox-shell.js\" defer\|src=\"nox-shell.js\"" $S/*.html | grep -v ":0" | wc -l
