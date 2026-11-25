#!/bin/bash
S=/workspace/nox/web/site/vendor/vidstack
head -c 600 $S/vidstack.iife.js; echo
grep -o 'customElements.define("[a-z-]*"' $S/vidstack.iife.js | head -60
grep -o 'media-[a-z-]*-layout' $S/vidstack.iife.js | sort -u
ls $S/player/layouts $S/player/styles $S/player/styles/default $S/player/styles/default/layouts
