set -x
N=/workspace/nox; P=$N/svc/pipeline; B=$P/fix6; O=$N/state/c_fix6.out; : > $O; exec >> $O 2>&1
cp $P/pipeline_svc.py $P/pipeline_svc.py.bak_c_fix6; python3 $B/patch_k3.py && python3 -m py_compile $P/pipeline_svc.py && echo pc_ok || { cp $P/pipeline_svc.py.bak_c_fix6 $P/pipeline_svc.py; echo rollback; }
pkill -f pipeline_svc.py; sleep 1; ( cd $P && nohup setsid $N/venv_living/bin/python pipeline_svc.py >$P/pipeline.log 2>&1 </dev/null & ); sleep 3; curl -s -m4 localhost:18217/health; echo
python3 - <<'PY'
import subprocess,re
Q=[("Столица Португалии?","Лиссабон"),("Кто открыл пенициллин?","Флеминг"),("Сколько секунд в минуте?","60"),("Назови столицу Японии","Токио"),("Какой химический символ у золота?","Au"),("Сколько будет 12*12?","144"),("Самая большая планета?","Юпитер"),("Кто написал Мастера и Маргариту?","Булгаков"),("Столица Испании?","Мадрид"),("Сколько континентов на Земле?","7|сем")]
cjk=re.compile(r"[぀-ヿ㐀-䶿一-鿿]"); bad=hier=empty=slow=0
for q,exp in Q:
    try: o=subprocess.run(["python3","/workspace/nox/svc/pipeline/c_test.py",q,"cf6%d"%abs(hash(q)),"60"],capture_output=True,text=True,timeout=80).stdout
    except Exception as e: o="ERR"
    m=re.search(r"first_delta_s= ([\d.]+|None)",o); fd=float(m.group(1)) if m and m.group(1)!="None" else None
    a=(re.search(r"ANSWER: (.*)",o) or [0,""])[1]; ok=bool(re.search(exp,a,re.I)); c=bool(cjk.search(o))
    hier+=c; bad+=(not ok); empty+=(not a.strip()); slow+=(fd is None or fd>8)
    print("Q:",q,"| t1=",fd,"| cjk=",c,"| верно=",ok,"|",a[:90])
print("ИТОГ: иероглифов",hier,"неверных",bad,"пустых",empty,"медленнее 8с",slow)
PY
echo FINISHED
