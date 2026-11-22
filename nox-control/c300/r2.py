import shutil, time, subprocess
p="/root/nox/web_server.py"; s=open(p).read(); shutil.copy(p,p+".bak_r2_"+time.strftime("%H%M%S"))
old="Обращение «Создатель» — основное."
new=("Обращение «Создатель» — основное. Не повторяй шаблоны из своих правил дословно (никакого «хочу поглотить X» с буквой X — "
     "называй конкретную вещь или не предлагай). Не начинай ответ с «я проснулся» и не пересказывай своё состояние без вопроса.")
print(s.count(old)); s=s.replace(old,new,1); open(p,"w").write(s)
print("compile", subprocess.run(["python3","-m","py_compile",p]).returncode)
