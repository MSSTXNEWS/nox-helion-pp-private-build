V=/workspace/nox/invoke
/workspace/nox/invoke/bin/python - <<'P'
import re,glob
n=0
for f in glob.glob('/workspace/nox/invoke/lib/python3.10/site-packages/invokeai/**/*.py',recursive=True):
    s=open(f,encoding='utf-8').read()
    def fix(m):
        names=[x.strip() for x in m.group(1).replace('\n',' ').strip('() ').split(',') if x.strip()]
        if 'Self' not in names: return m.group(0)
        rest=[x for x in names if x!='Self']
        out=('from typing import '+', '.join(rest)+'\n') if rest else ''
        return out+'from typing_extensions import Self\n'
    t=re.sub(r'^from typing import (\([^)]*\)|[^\n]*)\n',fix,s,flags=re.M)
    if t!=s: open(f,'w',encoding='utf-8').write(t); n+=1
print('patched',n)
P
for i in 1 2 3; do
  pkill -f invokeai-web; sleep 1
  nohup setsid bash /workspace/nox/svc/start_extra.sh >/dev/null 2>&1 &
  sleep 60
  curl -s -m5 -o /dev/null -w "api %{http_code}\n" localhost:9090/api/v1/app/version | grep -q "api 200" && break
  grep -v "^\s*File\|^\s\s\|^W\|^I0\|^E0\|^2026" /workspace/nox/svc/logs/invoke.log | tail -3 | cut -c1-240
done
curl -s -m5 -w "\napi %{http_code}\n" localhost:9090/api/v1/app/version
curl -s -m5 localhost:9090/ | grep -o '<script[^>]*>\|<link[^>]*>\|<base[^>]*>' | head -6
