S=/workspace/nox/web/site; N=/workspace/nox/build_a/node_modules
sed -n 150,177p $S/nox-wow.js | cut -c1-900
echo ====; head -c 300 $S/vendor/fx/motion.js; echo; head -c 200 $S/vendor/fx/gsap.min.js; echo; ls $S/vendor/motion/dist | head; ls $S/vendor/tsparticles | head
echo ==== arwes; node -e "console.log(Object.keys(require('/workspace/nox/build_a/node_modules/@arwes/frames')).join(' '))" 2>&1 | head -5
ls /workspace/nox/build_a/llm-viz/out | head; du -sh /workspace/nox/build_a/llm-viz/out
tail -c 600 /workspace/nox/build_a/llm2.log | head -5
