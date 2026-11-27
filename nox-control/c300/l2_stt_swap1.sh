echo "K1: l2_stt_swap1"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; VV=$N/voice_venv; M=$N/voice_models/whisper-large-v3-turbo
L=$(ls -d $N/venv/lib/python3*/site-packages/nvidia/*/lib 2>/dev/null | tr '\n' ':'); L=${L%:}
cat > /etc/supervisor/conf.d/nox_stt.conf <<CF
[program:nox_stt]
command=$VV/bin/python $N/c300_voice/voice/stt_server.py
directory=$N/c300_voice
environment=NOX_STT_MODEL="$M",NOX_STT_DEVICE="cuda",NOX_STT_COMPUTE="float16",NOX_STT_THREADS="4",NOX_STT_PORT="8093",NOX_VOICE_VENV="$VV",NOX_VOICE_MODELS="$N/voice_models",LD_LIBRARY_PATH="$L",PATH="$VV/bin:/usr/local/bin:/usr/bin:/bin"
autostart=true
autorestart=true
startsecs=10
stdout_logfile=$N/svc/logs/stt.log
stderr_logfile=$N/svc/logs/stt.log
stopasgroup=true
killasgroup=true
CF
kill 2528 2>/dev/null; sleep 2
supervisorctl reread | tail -1; supervisorctl update | tail -1
ok=0; for i in $(seq 1 30); do h=$(curl -s -m 3 127.0.0.1:8093/health); echo "$h" | grep -q '"ready": true' && { ok=1; break; }; sleep 3; done
echo "$h" | head -c 400; echo
if [ $ok = 0 ]; then echo ROLLBACK; supervisorctl stop nox_stt; rm -f /etc/supervisor/conf.d/nox_stt.conf; supervisorctl reread|tail -1; supervisorctl update|tail -1; pkill -f c300_voice/voice/stt_server.py; NOX_STT_MODEL=small NOX_STT_DEVICE=cpu NOX_STT_THREADS=4 NOX_VOICE_VENV=$VV NOX_VOICE_MODELS=$N/voice_models NOX_VOICE_RUNDIR=$N/c300_voice/run NOX_VOICE_LOGDIR=$N/agent/out bash $N/c300_voice/voice/start_voice.sh stt | tail -2; tail -n 8 $N/svc/logs/stt.log | cut -c1-200; exit 0; fi
python3 - <<'PY'
import json,base64,time,urllib.request as ur,wave,io
rq=ur.Request("http://127.0.0.1:8094/synth",data=json.dumps({"text":"Привет, меня зовут Нокс. Сегодня в Севастополе хорошая погода.","lang":"ru","format":"json"}).encode(),headers={"Content-Type":"application/json"})
ev=json.loads(ur.urlopen(rq,timeout=60).read())["events"]; pcm=b"".join(base64.b64decode(e["pcm"]) for e in ev if e.get("pcm"))
b=io.BytesIO(); w=wave.open(b,"wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm); w.close()
for i in range(3):
    t=time.time(); rq=ur.Request("http://127.0.0.1:8093/transcribe?language=ru",data=b.getvalue(),headers={"Content-Type":"audio/wav"}); r=json.loads(ur.urlopen(rq,timeout=60).read()); print("transcribe %.2fs"%(time.time()-t),str(r.get("text"))[:120])
PY
supervisorctl status nox_stt; nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
