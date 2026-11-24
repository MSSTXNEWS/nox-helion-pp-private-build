import json, urllib.request, base64, wave, io, time
TXT="Привет! Я NOX. Сегодня хороший день, давай поработаем."
def synth(backend_hint=None):
    b={"text":TXT,"lang":"ru"}
    r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8091/tts/synth",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=120)
    pcm=b""; rate=None; be=set()
    for line in r:
        line=line.decode().strip()
        if not line.startswith("data:"): continue
        d=json.loads(line[5:])
        if d.get("type")=="audio": pcm+=base64.b64decode(d["pcm_b64"]); rate=d["sample_rate"]; be.add(d.get("backend"))
    return pcm, rate, be
pcm, rate, be = synth()
print("backend", be, "rate", rate, "sec %.1f"%(len(pcm)/2/(rate or 1)))
buf=io.BytesIO(); w=wave.open(buf,"wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm); w.close()
open("/tmp/tts_test.wav","wb").write(buf.getvalue())
for ct in ("audio/wav",):
    try:
        r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8091/stt/transcribe",buf.getvalue(),{"Content-Type":ct}),timeout=120)
        print("STT:", r.read().decode()[:300])
    except Exception as e: print("stt err", e, getattr(e,"read",lambda:b"")()[:200])
