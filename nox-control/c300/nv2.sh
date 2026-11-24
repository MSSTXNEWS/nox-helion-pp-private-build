#!/bin/bash
S=/workspace/nox/web/site; sed -e 's/  */ /g' $S/nox-nav.js | head -c 5500
