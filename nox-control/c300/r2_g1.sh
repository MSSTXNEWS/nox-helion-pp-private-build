cd /workspace/nox/web/site/qa
python3 - <<'P'
import json,time
a=json.load(open('audit.json'))
V=[]
for k in ('settings','cinema','photo','atlas','index','news','chat','finance','assistant'):
    r=a.get(k,{}); 
    if not r: continue
    bad=[i for i,v in r['items'].items() if v['status']=='rework' and i!='20']
    print(k,r['ts'],r['ARU'],r['wow'],bad,(r.get('fix') or [''])[0][:100])
    V.append(f"| {k} | {r['ts']} | {r['ARU']} | возврат | п.{','.join(bad)}; handmade/U<8 |")
open('r2_verdicts.md','w',encoding='utf-8').write("\n## Вердикты R2 (приёмка: A,R,U>=8, п.1,6,8,9,23)\n\n| Стр | Проверено | A/R/U | Вердикт | Главная причина |\n|---|---|---|---|---|\n"+"\n".join(V)+"\n")
P
cp -n /workspace/nox/s5_sum.py /workspace/nox/s5_sum.py.bak_r2_2
grep -q r2_verdicts /workspace/nox/s5_sum.py || echo 'open(S+"/summary.md","a",encoding="utf-8").write(open(S+"/r2_verdicts.md",encoding="utf-8").read())' >> /workspace/nox/s5_sum.py
grep -n "^DONE" /tmp/r2_audit.log | tail -3
