echo "K1: v8_dbg2"
PY=/workspace/nox/voice/venv/bin/python
$PY - <<'P'
import http.client, json, io, wave, time, numpy as np
def post(h,path,body,ct="application/json"):
    c=http.client.HTTPConnection("127.0.0.1",h,timeout=60);c.request("POST",path,body,{"Content-Type":ct});r=c.getresponse();return r.status,r.read()
s,w_=post(18797,"/tts",json.dumps({"text":"Привет, как дела, расскажи коротко, что нового."}).encode())
w=wave.open(io.BytesIO(w_));sr=w.getframerate();a=np.frombuffer(w.readframes(w.getnframes()),dtype="<i2").astype("float32")
q=np.interp(np.arange(0,len(a),sr/16000.0),np.arange(len(a)),a).astype("<i2").tobytes()
print("sr",sr,"bytes16",len(q))
s,b=post(8093,"/stream/start",json.dumps({"language":"ru","partial":0.5}).encode());print("start",s,b[:200]);sid=json.loads(b)["id"]
for k in range(0,len(q)-1023,1024):
    s,b=post(8093,"/stream/%s/chunk"%sid,q[k:k+1024],"application/octet-stream")
    if b!=b'' and k%20480==0 or b'final' in b or b'partial' in b: print(k,s,b[:300])
for i in range(30):
    s,b=post(8093,"/stream/%s/chunk"%sid,b"\0"*1024,"application/octet-stream")
    if b'final' in b or b'end_of_turn' in b: print("sil",i,s,b[:400]);break
s,b=post(8093,"/stream/%s/finish"%sid,b"");print("finish",s,b[:400])
P
