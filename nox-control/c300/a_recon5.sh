S=/workspace/nox/web/site
sed -n 85,99p $S/nox-wow.js | cut -c1-400
echo ======; sed -n 200,262p $S/nox-wow.js | cut -c1-700
echo ======; ls $S/vendor/nox-x/react $S/vendor/nox-x/fx2 | head -30
echo; cat $S/vendor/licenses/gsap/* 2>/dev/null | head -8
echo; curl -s -m5 "http://127.0.0.1:8091/api/nox/training/status" | head -c 300; ls -la /workspace/nox/agent/out/*.log | tail -12; tail -n 3 /workspace/nox/agent/out/train_student4.log | cut -c1-300; ls /workspace/nox/web/site/qa | head -20
