echo "K1: e7_dbg"; N=/workspace/nox; echo "md5=$(md5sum < $N/mods/weekly_exam.py | cut -c1-8) stop_at=$(grep -c 'stop_at=3.0' $N/mods/weekly_exam.py)"
NOX_ROOT=$N python3 -I - <<'PY'
import sys,time,json; sys.path.insert(0,"/workspace/nox/mods"); import weekly_exam as w
for q in ("Считай вслух от 1 до 3000, каждое число с новой строки, без пропусков и комментариев.","Напиши очень длинный рассказ на 5000 слов про пустыню."):
    r=w.turn("qa-exam-dbg",q,stop_at=3.0,timeout=60); print("end=%s ttft=%s total=%.1f stop_s=%s len=%d"%(r["end"],r["ttft"] and round(r["ttft"],2),r["total"],r["stop_s"],len(r["text"])))
    w.stop_turn("qa-exam-dbg")
import urllib.request
try: print(w.post(w.CHAT+"/api/turn/stop",{"conversation_id":"qa-none"},5).read()[:200])
except Exception as e: print("stop_ep",type(e).__name__,str(e)[:100])
PY
echo END
