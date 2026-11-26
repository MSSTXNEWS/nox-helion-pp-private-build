import subprocess,re,sys
Q=[("Привет! Как дела?",None),("Столица Канады?","Оттав"),("Сколько будет 15*15?","225"),("Кто написал Преступление и наказание?","Достоевск"),("Сколько часов в сутках?","24"),("Какая самая длинная река в России?","Лен|Об"),("Назови столицу Германии","Берлин"),("Химический символ серебра?","Ag"),("Кто изобрёл телефон?","Белл|Bell"),("Объясни простыми словами что такое гравитация","")]
cjk=re.compile(r"[぀-ヿ㐀-䶿一-鿿]"); bad=hier=empty=slow=0; tag=sys.argv[1]
for i,(q,exp) in enumerate(Q):
    try: o=subprocess.run(["python3","/workspace/nox/svc/pipeline/c_test.py",q,"qa-%s%d"%(tag,i),"60"],capture_output=True,text=True,timeout=80).stdout
    except Exception as e: o="ERR"
    m=re.search(r"first_delta_s= ([\d.]+|None)",o); fd=float(m.group(1)) if m and m.group(1)!="None" else None
    a=(re.search(r"ANSWER: (.*)",o) or [0,""])[1]; ok=(not exp) or bool(re.search(exp,a,re.I)); c=bool(cjk.search(o))
    hier+=c; bad+=(not ok); empty+=(not a.strip()); slow+=(fd is None or fd>8)
    print("Q:",q,"| t1=",fd,"| cjk=",c,"| верно=",ok,"|",a[:90],flush=True)
print("ИТОГ: иероглифов",hier,"неверных",bad,"пустых",empty,"медленнее 8с",slow)
