#!/bin/bash
S=/workspace/nox/web/site
grep -o ".\{160\}\.attrs.\{80\}" $S/nox-photo.js | head -5
grep -o "openF.\{200\}" $S/nox-photo.js | head -3
