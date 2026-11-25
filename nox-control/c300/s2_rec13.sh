#!/bin/bash
S=/workspace/nox/web/site/vendor
ls $S/fabric $S/fabric/dist 2>&1 | head -12; cat $S/fabric/package.json 2>/dev/null | grep '"version"'
ls $S/three/build | head; ls $S/planets/2k | wc -l
ls $S/transformers-js $S/shaka-player $S/vidstack 2>&1 | head -20
curl -s -m5 -X POST http://127.0.0.1:8091/api/creative -H 'Content-Type: application/json' -d '{}' | head -c 200
