import shutil, time, subprocess
p="/root/nox/web_server.py"; s=open(p).read(); shutil.copy(p,p+".bak_rq_"+time.strftime("%H%M%S"))
old="отвечай по существу, живо и кратко, по-русски."
new=("отвечай по существу заданного вопроса, живо и содержательно, по-русски: на приветствие или реплику — 1–2 живые фразы, "
     "на вопрос по делу — конкретный ответ с фактами, причинами и шагами (3–8 предложений). Не отделывайся общими словами и лозунгами, "
     "не заканчивай шаблонами вроде «Говори, что нужно», «Принял. Готов». Обращение «Создатель» — основное.")
print("rules", s.count(old)); s=s.replace(old,new)
print("hist", s.count("_B = 3500")); s=s.replace("_B = 3500","_B = 6000")
open(p,"w").write(s); r=subprocess.run(["python3","-m","py_compile",p],capture_output=True,text=True); print("compile",r.returncode)
