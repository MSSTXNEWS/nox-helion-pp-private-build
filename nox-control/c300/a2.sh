set -u
S=/workspace/nox/web/site
mkdir -p /workspace/nox/tools/node && cd /workspace/nox/tools/node
if [ ! -x bin/node ]; then
  V=$(curl -s https://nodejs.org/dist/index.json | python3 -c "import json,sys;d=[x for x in json.load(sys.stdin) if x['lts'] and x['version'].startswith('v22')];print(d[0]['version'])")
  echo node $V; curl -fsSL https://nodejs.org/dist/$V/node-$V-linux-x64.tar.xz | tar xJ --strip-components=1
fi
export PATH=/workspace/nox/tools/node/bin:$PATH; node -v; npm -v
rm -rf /tmp/nkb && mkdir /tmp/nkb && cd /tmp/nkb && npm init -y >/dev/null && npm i ninja-keys esbuild --no-audit --no-fund 2>&1 | tail -2
echo "import 'ninja-keys';" > e.js
npx esbuild e.js --bundle --format=esm --minify --outfile=$S/vendor/ninja-keys/ninja-keys.js 2>&1 | tail -3
cp node_modules/ninja-keys/LICENSE $S/vendor/ninja-keys/LICENSE
ls -la $S/vendor/ninja-keys; df -h /workspace | tail -1
