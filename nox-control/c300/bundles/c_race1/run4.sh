set -x
N=/workspace/nox; S=$N/web/site; P=$N/svc/pipeline; O=$N/state/c_race4.out; : > $O
exec >> $O 2>&1
echo "== restore audit.json if broken"
python3 - <<'PY'
import json,shutil,glob
p="/workspace/nox/web/site/qa/audit.json"
try: json.load(open(p)); print("audit.json valid")
except Exception as e:
    print("audit.json BROKEN",e)
    for b in ("/workspace/nox/web/site/qa/audit.json.bak_c_5","/workspace/nox/web/site/qa/audit.json.bak_c_1"):
        try: json.load(open(b)); shutil.copy(b,p); print("restored from",b); break
        except Exception as e2: print("bak bad",b,e2)
PY
echo "== state"; curl -s -m3 localhost:8200/running; echo; curl -s -m3 localhost:18217/quota; echo; pgrep -fa "qa_audit|playwright" | cut -c1-100 | head -3
echo "== pool probe (1 request)"; curl -s -m20 localhost:8793/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"pollinations/openai","messages":[{"role":"user","content":"Столица Франции? Одно слово."}],"max_tokens":20}' | cut -c1-300; echo
echo "== 5 real questions"
for q in "Привет, как дела?" "Сколько будет 17*23?" "Назови три столицы Европы" "Объясни простыми словами что такое DNS" "Что лучше для сервера: Python или Go? Коротко"; do timeout 110 python3 $P/c_test.py "$q" crace$RANDOM 100; done
echo "== forced race x2"
for q in "Назови пять цветов радуги" "Чем отличается TCP от UDP? Коротко"; do timeout 110 python3 $P/c_test.py "$q" crace$RANDOM 100 '{"race_s":0.3}'; done
curl -s -m3 localhost:18217/quota; echo; tail -4 $N/state/pipe_err.log
echo TESTS_DONE
echo "== qa_audit chat (long)"; cd $N && timeout 2400 $N/venv/bin/python $N/qa_audit.py chat.html | tail -6
python3 - <<'PY'
import json,shutil
p="/workspace/nox/web/site/qa/audit.json"
try:
    d=json.load(open(p)); print("AUDIT chat:",json.dumps(d.get("chat"),ensure_ascii=False)[:2500])
except Exception as e:
    print("audit.json broken after run",e); shutil.copy("/workspace/nox/web/site/qa/audit.json.bak_c_5",p); print("restored")
PY
echo FINISHED
