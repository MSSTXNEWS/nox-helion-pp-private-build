echo "K1: v8_deploy"
N=/workspace/nox; U=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
PY=$N/voice/venv/bin/python; TS=$(date +%s); NEW=/tmp/v8_voice_service.py; CONF=/etc/supervisor/conf.d/nox_voice.conf
SHA_EXPECT=e34e62c4a4b2159aa0396f13ad2db05d96a5f6d4a5a69afb2be2fcefc543bcb0
curl -fsSL "$U/voice_service_v8.py?x=$RANDOM" -o $NEW || { echo "fetch fail"; exit 1; }
[ "$(sha256sum $NEW | cut -c1-64)" = "$SHA_EXPECT" ] || { echo "sha mismatch"; exit 1; }
$PY -m py_compile $NEW || { echo "syntax fail"; exit 1; }
cp -p $N/mods/voice_service.py $N/mods/voice_service.py.bak_v8_$TS; cp -p $CONF $CONF.bak_v8_$TS
echo "backup ts=$TS"
if [ ! -s $N/voice/silero_vad.onnx ]; then rm -rf /tmp/v8sv; mkdir -p /tmp/v8sv; $N/voice/venv/bin/pip download --no-deps -q -d /tmp/v8sv silero-vad 2>&1 | tail -1; python3 -c "
import zipfile,glob
z=zipfile.ZipFile(glob.glob('/tmp/v8sv/*.whl')[0]);n=[x for x in z.namelist() if x.endswith('data/silero_vad.onnx')][0];open('$N/voice/silero_vad.onnx','wb').write(z.read(n));print('silero',n)"; fi
ls -la $N/voice/silero_vad.onnx | awk '{print "silero bytes",$5}'
curl -fsSL "$U/v8_bench.py?x=$RANDOM" -o /tmp/v8_bench.py
# --- тест на :18899
mkdir -p /tmp/v8t && cp $NEW /tmp/v8t/voice_service.py && cp $N/mods/piper_tts.py /tmp/v8t/
ENVS=$(tr '\0' '\n' < /proc/$(pgrep -f "python3 -I $N/mods/voice_service.py" | head -1)/environ | grep -E "^NOX_" | grep -v NOX_VOICE_PORT | tr '\n' ' ')
cd /tmp/v8t; env $ENVS NOX_VOICE_PORT=18899 setsid nohup $PY -I voice_service.py >/tmp/v8t/log 2>&1 7>&- & TP=$!
sleep 20; echo "test health: $(curl -s -m5 127.0.0.1:18899/health)"
echo "== bench TEST port"; PORT=18899 $PY /tmp/v8_bench.py 2>&1 | tail -3
kill $TP 2>/dev/null; tail -n 3 /tmp/v8t/log | cut -c1-200
# --- cutover
echo "== cutover"
cp $NEW $N/mods/voice_service.py
sed -i "s#^command=python3 -I $N/mods/voice_service.py#command=$PY -I $N/mods/voice_service.py#" $CONF; grep "^command" $CONF
supervisorctl reread >/dev/null 2>&1; supervisorctl update >/dev/null 2>&1; supervisorctl restart nox_voice 2>&1 | tail -2
OK=0; for i in $(seq 1 20); do sleep 3; H=$(curl -s -m4 127.0.0.1:18797/health); echo "$H" | grep -q '"ok": true' && { OK=1; break; }; done
echo "live health: $H"
if [ $OK = 1 ]; then CODE=$(curl -s -m30 -o /tmp/v8_t.wav -w "%{http_code}" -X POST 127.0.0.1:18797/tts -d '{"text":"Проверка голоса."}'); echo "tts http=$CODE bytes=$(stat -c %s /tmp/v8_t.wav)"; [ "$CODE" = 200 ] && [ "$(stat -c %s /tmp/v8_t.wav)" -gt 20000 ] || OK=0; fi
if [ $OK != 1 ]; then echo "ROLLBACK"; cp -p $N/mods/voice_service.py.bak_v8_$TS $N/mods/voice_service.py; cp -p $CONF.bak_v8_$TS $CONF; supervisorctl reread >/dev/null 2>&1; supervisorctl update >/dev/null 2>&1; supervisorctl restart nox_voice 2>&1 | tail -1; sleep 5; curl -s -m4 127.0.0.1:18797/health; exit 1; fi
echo "== bench LIVE after"; PORT=18797 $PY /tmp/v8_bench.py 2>&1 | tail -3
echo "rollback: cp mods/voice_service.py.bak_v8_$TS + $CONF.bak_v8_$TS, supervisorctl update/restart nox_voice"
