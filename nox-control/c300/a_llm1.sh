export PATH=/workspace/nox/tools/node/bin:$PATH
cd /workspace/nox/build_a/llm-viz; cat next.config.js; ls src src/pages src/app 2>/dev/null | head -30
cat > /workspace/nox/build_a/llm.sh <<'X'
export PATH=/workspace/nox/tools/node/bin:$PATH
cd /workspace/nox/build_a/llm-viz
cp -n next.config.js next.config.js.orig_a
npm i --no-audit --no-fund --legacy-peer-deps 2>&1 | tail -5
echo INSTALLED
X
nohup setsid bash /workspace/nox/build_a/llm.sh > /workspace/nox/build_a/llm.log 2>&1 &
sleep 100; tail -8 /workspace/nox/build_a/llm.log
