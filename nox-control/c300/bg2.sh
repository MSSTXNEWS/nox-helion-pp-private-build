#!/bin/bash
S=/workspace/nox/web/site; cat $S/nox-wow-bg.js; echo; grep -l "export async function startSun\|startSun" $S/*.js | head
f=$(grep -l "export async function startSun\|export function startSun\|startSun =" $S/*.js | head -1); echo "== $f $(wc -c <$f)"; grep -n "setPixelRatio\|pixelRatio\|level\b\|'high'\|'eco'\|Bloom\|antialias\|toneMapping\|resolution\|DPR\|dpr" $f | head -30 | cut -c1-180
