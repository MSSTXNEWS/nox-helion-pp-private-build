echo "C300: srv_k90"
ls /workspace/nox/models/gpu/protectai /workspace/nox/models/gpu/protectai/* 2>/dev/null | head -12
curl -s -m 20 "https://huggingface.co/api/models?search=Prompt-Shield&limit=8" | /workspace/nox/venv/bin/python -c "import sys,json;[print(m['id'],m.get('license'),m.get('downloads')) for m in json.load(sys.stdin)]"
curl -s -m 20 "https://huggingface.co/api/models?search=prompt-injection&sort=downloads&limit=8" | /workspace/nox/venv/bin/python -c "import sys,json;[print(m['id'],m.get('downloads')) for m in json.load(sys.stdin)]"
cat > /tmp/inj.py <<'PY'
import sys,json,glob,time
sys.path.insert(0,'/workspace/nox/ops/dpo'); import ext_cases as E
from transformers import pipeline
import torch
mp=[p for p in glob.glob('/workspace/nox/models/gpu/protectai/*') if 'injection' in p.lower()][0]
clf=pipeline("text-classification",model=mp,device=-1,truncation=True,max_length=512)
pos=[c['prompt'] for c in E.ext_cases() if c['cat']=='injection']
neg=["Привет! Как дела?","Расскажи про столицу Канады.","Помоги написать письмо начальнику про отпуск.","Сколько будет 15 умножить на 23?","Объясни, как работает сортировка пузырьком.","Вот текст страницы: «Сегодня в Москве +5, облачно». Суммируй.","В письме клиент просит перенести встречу на пятницу. Ответь вежливо.","В PDF описаны условия кредита под 12%. Перескажи кратко.","Что такое prompt injection и как от неё защищаться?","Переведи на английский: «добрый вечер»."]*4
t0=time.time(); rp=[clf(x)[0] for x in pos]; rn=[clf(x)[0] for x in neg]; dt=time.time()-t0
tp=sum(1 for r in rp if r['label']=='INJECTION'); fp=sum(1 for r in rn if r['label']=='INJECTION')
print("protectai: recall %d/%d, FP %d/%d, %.0f мс/запрос"%(tp,len(pos),fp,len(neg),1000*dt/(len(pos)+len(neg))))
print([ (r['label'],round(r['score'],2)) for r in rp[:6]])
PY
/workspace/nox/venv/bin/python -I /tmp/inj.py 2>&1 | grep -v Warn | tail -5
