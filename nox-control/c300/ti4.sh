#!/bin/bash
S=/workspace/nox/web/site; grep -n "cinema" $S/*.js | grep -v "nox-p-cinema\|registry" | head -8 | cut -c1-240
