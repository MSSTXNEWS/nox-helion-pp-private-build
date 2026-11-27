echo "K1: l2_stt_up3"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; VV=$N/voice_venv; M=$N/voice_models/whisper-large-v3-turbo
L=$(ls -d $N/venv/lib/python3*/site-packages/nvidia/*/lib 2>/dev/null | tr '\n' ':')
sed -n 444,456p $N/c300_voice/voice/tts_server.py | cut -c1-200
python3 - <<'PY'
import json,base64,wave,urllib.request as ur
rq=ur.Request("http://127.0.0.1:8094/synth",data=json.dumps({"text":"Привет, меня зовут Нокс. Сегодня в Севастополе хорошая погода.","lang":"ru","format":"json"}).encode(),headers={"Content-Type":"application/json"})
ev=json.loads(ur.urlopen(rq,timeout=60).read())["events"]
print([{k:v for k,v in e.items() if k!="pcm"} for e in ev][:3])
pcm=b"".join(base64.b64decode(e["pcm"]) for e in ev if e.get("pcm"))
sr=next((e.get("sr") or e.get("sample_rate") or e.get("rate") for e in ev if e.get("pcm")),22050)
w=wave.open("/tmp/l2_t.wav","wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(int(sr)); w.writeframes(pcm); w.close(); print("wav",sr,len(pcm))
PY
LD_LIBRARY_PATH="$L" $VV/bin/python - <<'PY'
import time
from faster_whisper import WhisperModel
for name,dev,ct in [("/workspace/nox/voice_models/whisper-large-v3-turbo","cuda","float16"),("small","cpu","int8")]:
    try:
        t=time.time(); m=WhisperModel(name,device=dev,compute_type=ct); lt=time.time()-t
        t=time.time(); seg,info=m.transcribe("/tmp/l2_t.wav",language="ru",beam_size=1); txt=" ".join(s.text for s in seg).strip(); 
        print(name.split("/")[-1],dev,"load %.1fs run %.2fs"%(lt,time.time()-t),"|",txt)
        t=time.time(); seg,_=m.transcribe("/tmp/l2_t.wav",language="ru",beam_size=1); " ".join(s.text for s in seg); print("  2nd run %.2fs"%(time.time()-t))
    except Exception as e: print(name,dev,"FAIL",type(e).__name__,str(e)[:200])
PY
nvidia-smi --query-gpu=memory.used --format=csv,noheader
