B=/workspace/nox/build_a; mkdir -p $B; cd $B
cat > inst.sh <<'X'
export PATH=/workspace/nox/tools/node/bin:$PATH; cd /workspace/nox/build_a
[ -f package.json ] || npm init -y >/dev/null
npm i --no-audit --no-fund esbuild react react-dom @xyflow/react @assistant-ui/react deep-chat 3d-force-graph three @arwes/frames @arwes/animated @arwes/bgs @arwes/text echarts @cosmos.gl/graph 2>&1 | tail -15
echo NPMDONE
[ -d llm-viz ] || git clone --depth 1 https://github.com/bbycroft/llm-viz.git 2>&1 | tail -2
echo CLONEDONE
X
nohup setsid bash inst.sh > inst.log 2>&1 &
sleep 150; cat inst.log | tail -30
