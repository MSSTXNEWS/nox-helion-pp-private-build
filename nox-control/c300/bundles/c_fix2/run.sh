set -x
N=/workspace/nox; S=$N/web/site; P=$N/svc/pipeline; B=$P/fix2; O=$N/state/c_fix2.out; : > $O; exec >> $O 2>&1
echo "== 1. pipeline: CJK/coder фильтр + обход кэша"; cp $P/pipeline_svc.py $P/pipeline_svc.py.bak_c_fix2; python3 $B/patch_cjk.py && python3 -m py_compile $P/pipeline_svc.py && echo pc_ok || { cp $P/pipeline_svc.py.bak_c_fix2 $P/pipeline_svc.py; echo rollback; }
pkill -f pipeline_svc.py; sleep 1; ( cd $P && nohup setsid $N/venv_living/bin/python pipeline_svc.py >$P/pipeline.log 2>&1 </dev/null & ); sleep 3; curl -s -m4 localhost:18217/health; echo
echo "== 2. site"; cp -n $S/nox-vt.css $S/nox-vt.css.bak_c_fix2; grep -q "c_fix2: лупа" $S/nox-vt.css || cat $B/vt_search.css >> $S/nox-vt.css
cp $B/nox-chat-clean.js $B/nox-chat-clean.css $S/; sed -i 's#nox-chat-clean.css?v=[0-9]*#nox-chat-clean.css?v=4#;s#nox-chat-clean.js?v=[0-9]*#nox-chat-clean.js?v=4#' $S/chat.html; grep -c "clean.*v=4" $S/chat.html; tail -c 300 $S/nox-vt.css
echo "== 3. 10 вопросов с проверкой фактов и CJK"
rm -f $N/state/c_fix2.rows; python3 - <<'PY'
import subprocess,re,json
Q=[("Привет!",None),("Столица Австралии?","Канберр"),("Столица Франции?","Париж"),("Скажи 2+2","4"),("Сколько будет 17*23?","391"),("Кто написал Войну и мир?","Толст"),("Сколько дней в феврале високосного года?","29"),("Переведи hello на французский","onjour"),("Кто написал Евгения Онегина?","Пушкин"),("Сколько планет в Солнечной системе?","8|восем")]
cjk=re.compile(r"[぀-ヿ㐀-䶿一-鿿]"); bad=0; hier=0; slow=0; empty=0
for q,exp in Q:
    try: o=subprocess.run(["python3","/workspace/nox/svc/pipeline/c_test.py",q,"cfx%d"%abs(hash(q)),"90"],capture_output=True,text=True,timeout=110).stdout
    except Exception as e: o="ERR "+str(e)
    m=re.search(r"first_delta_s= ([\d.]+|None)",o); fd=float(m.group(1)) if m and m.group(1)!="None" else None
    a=(re.search(r"ANSWER: (.*)",o) or [0,""])[1]; ok=(exp is None) or bool(re.search(exp,a,re.I))
    c=bool(cjk.search(o)); hier+=c; bad+=(not ok); empty+=(not a.strip()); slow+=(fd is None or fd>8)
    print("Q:",q,"| t1=",fd,"| cjk=",c,"| верно=",ok,"|",a[:110].replace("\n"," "))
print("ИТОГ: иероглифов",hier,"неверных",bad,"пустых",empty,"медленнее 8с",slow)
PY
echo FINISHED
