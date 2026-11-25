echo "C300: k5_probe_4"
cd /workspace/nox/web/site/vendor
ls -d *animate* *hover* *magic* *auto* *gsap* *lottie* *motion* *anime* *aos* *wow* *tsparticles* 2>/dev/null
for d in animate.css hover.css magic.css gsap lottie-web motion; do [ -d $d ] && { echo "## $d"; find $d -maxdepth 2 -type f | head -8 | xargs ls -la | awk '{print $5,$9}'; }; done
grep -iE 'animate|hover|magic|gsap|lottie|autoanim|motion' VENDOR_INDEX.md | cut -c1-200 | head -20
