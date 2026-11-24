cd /workspace/nox/web
for u in https://github.com https://registry.npmjs.org https://cdn.jsdelivr.net/npm/ninja-keys/package.json https://pypi.org/simple/invokeai/ https://repo.jellyfin.org https://nodejs.org/dist/index.json; do echo $u $(curl -s -o /dev/null -m 15 -w "%{http_code}" -L $u); done
grep -n "^class \|ThreadingHTTPServer\|def main\|serve_forever\|^Handler\|creative_proxy" pkg/server/web_server.py | cut -c1-200
sed -n 208,216p pkg/server/web_server.py | cut -c1-200
ls pkg/server | tr '\n' ' '; cat pkg/server/run_web.sh | head -20
python3 -c "import json;d=json.load(open('site/nav.json'));print(json.dumps(d['pages'],ensure_ascii=False)[:600])"
head -c 1500 site/nox-dock-wow.js
/workspace/nox/venv/bin/pip --version; /workspace/nox/venv/bin/python -c "import torch;print(torch.__version__)"; pip download invokeai --no-deps -d /tmp/ivk -q 2>&1 | tail -2; ls /tmp/ivk; apt-cache policy php-cli 2>/dev/null | head -3; lsb_release -d
