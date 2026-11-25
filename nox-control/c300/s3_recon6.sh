#!/bin/bash
S=/workspace/nox/web/site; cd $S
echo "#### vendor"; ls vendor | tr '\n' ' '; echo
echo "#### planets dirs"; ls vendor/planets 2>&1 | head -30; ls vendor/nox-planets 2>&1 | head -40; head -c 600 vendor/nox-planets/manifest.json
echo "#### three/gsap/motion/shoelace"; ls vendor/three/build 2>&1 | head -5; ls vendor/gsap 2>&1 | head -5; ls vendor/motion 2>&1 | head; ls vendor/shoelace 2>&1 | head -5; ls vendor/shoelace/cdn 2>&1 | head -8
echo "#### nox-wow-data PLANETS"; grep -n "PLANETS" nox-wow-data.js | head -3; grep -n "id: '" nox-wow-data.js | head -14 | cut -c1-260
echo "#### scene.html"; cat scene.html | cut -c1-300
echo "#### scene js"; ls nox-p-scene.js 2>&1; head -c 2500 nox-p-scene.js
echo "#### space api"; grep -n "setPlanet\|export" nox-space.js 2>/dev/null | head -10; ls nox-space* nox-wow* 2>/dev/null | head
echo "#### VENDOR_READY on server?"; ls /workspace/nox/web/site/vendor/planets 2>&1 | head -3; df -BG /workspace | tail -1
echo "#### shoelace register"; grep -n "shoelace" nox-nav.js nox-api.js nox-wow.css 2>/dev/null | head -5 | cut -c1-200; grep -o 'shoelace[^"]\{0,60\}' settings.html | head -3; grep -c "sl-tab-group\|sl-switch" nox-*.js | grep -v ":0" | head
