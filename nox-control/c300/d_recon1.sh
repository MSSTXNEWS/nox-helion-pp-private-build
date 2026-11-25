echo "C300: d_recon1"
df -BG /workspace | tail -1
export PATH=/workspace/nox/tools/node/bin:$PATH
node -v; npm -v; python3 --version; which uv java go pip pip3 git unzip 7z curl wget 2>&1
ls /workspace/nox/web/site/vendor | head -100
ls /workspace/nox/web/build/node_modules | wc -l
ls /workspace/nox/web/build/node_modules | head -150 | tr '\n' ' '
echo; ls /workspace/nox/svc /workspace/nox/svc/* 2>/dev/null | head -50
cat /workspace/nox/svc/start_all.sh | head -40
head -c 1500 /workspace/nox/web/pkg/server/svc_registry.json
echo; ls /workspace/nox/web/pkg/server | head -30
curl -sI -m 15 https://www.solarsystemscope.com/textures/download/2k_earth_daymap.jpg | head -5
nproc; free -g | head -2
