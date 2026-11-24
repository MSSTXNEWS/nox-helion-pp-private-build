#!/bin/bash
S=/workspace/nox/web/site; which node npm; df -h /workspace | tail -1
head -c 1500 $S/nox-registry.js; echo; grep -n "assistant.html\|'cinema'\|cinema.html" $S/nox-registry.js | head -5 | cut -c1-220
ls $S/vendor/nox-planets | head; find $S/vendor -iname "*earth*" | head -3
grep -o '<script[^>]*src="[^"]*"' $S/cinema.html | head -10
