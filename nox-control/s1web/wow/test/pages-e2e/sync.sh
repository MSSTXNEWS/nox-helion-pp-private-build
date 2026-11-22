#!/bin/bash
# собрать тестовый корень как на S1: плоско wow/* + pages/* ; vendor из стенда
W=/tmp/claude-0/wt-pages/nox-control/s1web/wow; R=/tmp/pagesroot
mkdir -p $R/wow; ln -sfn /tmp/vt/root/vendor $R/vendor
cp -f $W/*.js $W/*.css $W/*.html $W/*.json $R/ 2>/dev/null
cp -f $W/lottie-*.json $R/wow/; cp -rf $W/classic $R/ 2>/dev/null
cp -f $W/pages/* $R/ 2>/dev/null
for f in nox-v14-real.js favicon.svg; do [ -f $R/$f ] || cp /tmp/vt/root/$f $R/; done
