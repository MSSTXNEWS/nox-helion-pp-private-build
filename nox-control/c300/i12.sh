cat > /workspace/nox/invoke/lib/python3.10/site-packages/sitecustomize.py <<'P'
# NOX: скрыть сломанные пакеты основного venv от InvokeAI (xformers, torchao)
import importlib.util as _u, importlib.metadata as _m
_B = {'xformers', 'torchao', 'mslk'}
_f = _u.find_spec
def find_spec(name, package=None):
    if name.split('.')[0] in _B: return None
    return _f(name, package)
_u.find_spec = find_spec
_v = _m.version
def version(n):
    if n.lower().replace('_', '-') in _B: raise _m.PackageNotFoundError(n)
    return _v(n)
_m.version = version
import sys
class _Blk:
    def find_spec(self, name, path=None, target=None):
        if name.split('.')[0] in _B: raise ModuleNotFoundError(name)
sys.meta_path.insert(0, _Blk())
P
for i in 1 2; do
  pkill -f invokeai-web; sleep 1
  nohup setsid bash /workspace/nox/svc/start_extra.sh >/dev/null 2>&1 &
  sleep 70
  curl -s -m5 -o /dev/null -w "api %{http_code}\n" localhost:9090/api/v1/app/version | grep -q "api 200" && break
  grep -v "^\s*File\|^\s\s\|^W\|^I0\|^E0\|^2026\|^To enable" /workspace/nox/svc/logs/invoke.log | tail -3 | cut -c1-240
done
curl -s -m5 -w "\napi %{http_code}\n" localhost:9090/api/v1/app/version
curl -s -m5 localhost:9090/ | grep -o '<script[^>]*>\|<link[^>]*>\|<base[^>]*>' | head -6
