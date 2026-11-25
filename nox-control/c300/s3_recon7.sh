#!/bin/bash
S=/workspace/nox/web/site; cd $S
echo "#### nox-fx head"; head -c 1800 nox-fx.js
echo "#### vendor/motion"; ls vendor/motion vendor/motion/dist 2>&1 | head -12; ls vendor/nox-fx | head
echo "#### planets README"; cat vendor/nox-planets/README.md | head -12
echo "#### setPlanet"; grep -n "setPlanet" nox-wow-bg.js nox-nav.js | head -4 | cut -c1-200
echo "#### settings css"; grep -n "\.setg\|\.planets\|\.seg" nox-pages.css nox-unify.css nox-wow.css | head -12 | cut -c1-200
echo "#### nox-p-settings rest"; tail -c 2500 nox-p-settings.js
