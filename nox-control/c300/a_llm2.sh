cd /workspace/nox/build_a/llm-viz
python3 - <<'P'
s=open('next.config.js').read()
if 'basePath' not in s:
    s=s.replace("output: 'export',","output: 'export',\n  basePath: '/web/vendor/llm-viz',\n  assetPrefix: '/web/vendor/llm-viz',\n  productionBrowserSourceMaps: false,\n  typescript: {ignoreBuildErrors: true},\n  eslint: {ignoreDuringBuilds: true},",1).replace("productionBrowserSourceMaps: true,","")
    open('next.config.js','w').write(s)
P
cat > /workspace/nox/build_a/llm2.sh <<'X'
export PATH=/workspace/nox/tools/node/bin:$PATH
cd /workspace/nox/build_a/llm-viz
NODE_OPTIONS=--max-old-space-size=6000 npx next build 2>&1 | tail -40
echo BUILDDONE
X
nohup setsid bash /workspace/nox/build_a/llm2.sh > /workspace/nox/build_a/llm2.log 2>&1 &
sleep 120; tail -15 /workspace/nox/build_a/llm2.log
