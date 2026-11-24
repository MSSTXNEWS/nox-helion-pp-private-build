#!/bin/bash
S=/workspace/nox/web/site; grep -n "setLevel\|pixelRatio\|setPixelRatio\|level ===\|'high'\|'eco'\|antialias\|bloom\|UnrealBloom\|Bloom" $S/nox-wow-bg.js | head -25 | cut -c1-200; wc -c $S/nox-wow-bg.js
