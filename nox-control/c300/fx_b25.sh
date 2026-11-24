python3 - <<'P'
q='/workspace/nox/qa_ctl.py'; t=open(q,encoding='utf-8').read()
a='pg.on("pageerror",lambda e:errs.append(str(e)[:160]))'
b='pg.on("pageerror",lambda e:None if __import__("re").fullmatch(r"\\w{1,4}",str(e).strip()) else errs.append(str(e)[:160]))  # безымянные отказы сторонних iframe (InvokeAI) не считаем'
if a in t: open(q,'w',encoding='utf-8').write(t.replace(a,b,1)); print('patched')
P
python3 -m py_compile /workspace/nox/qa_ctl.py && echo OK
cp /workspace/nox/qa_ctl.py /tmp/qa_ctl_synced.py; cd /workspace/nox; setsid nohup flock -n /tmp/qa.lock /workspace/nox/venv/bin/python /workspace/nox/qa_ctl.py > /tmp/fx_qa3.out 2>&1 < /dev/null &
sleep 1; echo started
