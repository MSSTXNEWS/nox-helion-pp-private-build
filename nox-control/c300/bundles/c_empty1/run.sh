set -x
N=/workspace/nox; P=$N/svc/pipeline; O=$N/state/c_empty1.out; : > $O; exec >> $O 2>&1
echo "== /llm прямой (3 вопроса)"
for q in "Привет, как дела?" "Сколько будет 17*23?" "Что лучше: Python или Go? Коротко"; do
  /usr/bin/time -f "%es" curl -s -m 40 localhost:8810/llm -H 'Content-Type: application/json' -d "{\"prompt\":\"$q\",\"max_tokens\":120,\"backend\":\"main\"}" | cut -c1-220; echo
done
echo "== 10 вопросов через /api/turn"
i=0
for q in "Привет!" "Столица Австралии?" "Скажи 2+2" "Назови три цвета радуги" "Что такое DNS? коротко" "Чем TCP отличается от UDP? коротко" "Посоветуй книгу" "Кто написал Войну и мир?" "Переведи hello на французский" "Сколько дней в феврале високосного года?"; do
  i=$((i+1)); timeout 110 python3 $P/c_test.py "$q" cemp$RANDOM$i 100 | tee -a $N/state/c_empty1.rows
done
echo "== пустые ответы:"; grep -c "ANSWER: *$" $N/state/c_empty1.rows
echo "== сводка"; python3 - <<'PY'
import re
rows=open("/workspace/nox/state/c_empty1.rows").read().split("\n")
n=e=0;fd=[]
for l in rows:
    m=re.search(r"first_delta_s= ([\d.None]+)",l)
    if m:
        n+=1; v=m.group(1)
        if v=="None": e+=1
        else: fd.append(float(v))
print("вопросов",n,"без delta",e,"first_delta макс",max(fd) if fd else None,"сред",round(sum(fd)/len(fd),1) if fd else None, "<=8:",sum(1 for x in fd if x<=8))
PY
echo "== stage/race в логе"; tail -5 $N/state/pipe_err.log 2>/dev/null
echo FINISHED
