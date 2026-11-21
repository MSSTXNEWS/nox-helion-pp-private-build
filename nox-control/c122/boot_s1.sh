#!/bin/bash
# ДИСПЕТЧЕР S1 «Канада»: идемпотентный подъём всего чата после старта/перезапуска Vast.
# Порядок: репозиторий -> проверка модели в shm (при потере докачка) -> быстрый тир :8083 -> GLM :8081 -> шлюз :8082 -> веб :8091 -> голос :8093/:8094.
# Установка автозапуска: bash boot_s1.sh install   (пишет /root/onstart.sh и cron @reboot)
N=/root/nox; R=$N/repo; DL=$N/dl; LG=$N/logs; mkdir -p $LG
L=$(dirname $(find /usr/local /usr/lib -name "libcublas.so.12" 2>/dev/null | head -1))
export LD_LIBRARY_PATH=$L:/usr/local/cuda-12.9/targets/x86_64-linux/lib:$N/llama.cpp/build/bin:$LD_LIBRARY_PATH
BIN=$N/llama.cpp/build/bin/llama-server
log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a $LG/boot.log; }
up(){ curl -fs -m 3 "http://127.0.0.1:$1/health" >/dev/null 2>&1; }
if [ "$1" = install ]; then
  cp "$0" $N/boot_s1.sh 2>/dev/null; printf '#!/bin/bash\nbash /root/nox/boot_s1.sh >> /root/nox/logs/boot.log 2>&1 &\n' > /root/onstart.sh; chmod +x /root/onstart.sh
  (crontab -l 2>/dev/null | grep -v boot_s1; echo "@reboot bash /root/nox/boot_s1.sh >> /root/nox/logs/boot.log 2>&1") | crontab - 2>/dev/null
  echo installed; exit 0; fi
# 1. репозиторий
if [ -d $R/.git ]; then git -C $R pull -q 2>&1 | tail -1; else git clone -q --depth 1 https://github.com/MSSTXNEWS/nox-helion-pp-private-build $R; fi
C=$R/nox-control
# 2. модель в shm: 9 шардов по ~45 ГБ
n=$(ls /dev/shm/nox_glm/*.gguf 2>/dev/null | wc -l)
if [ "$n" -lt 9 ] || grep -q SOME_BAD $LG/redo.log 2>/dev/null; then
  log "shm: $n/9 шардов — докачка"; pgrep -f glm_redo >/dev/null || { cp $C/c100/glm_redo_s1.sh $N/glm_redo_s1.sh; nohup bash $N/glm_redo_s1.sh > $LG/redo.log 2>&1 & }
  log "ждём ALL_OK (запустите boot_s1.sh повторно)"; WAIT_MODEL=1
fi
# 3. быстрый тир
Q=$(find $DL/hf/qwen3_4b -name "*.gguf" | head -1)
if ! up 8083 && [ -n "$Q" ]; then
  log "fast tier :8083"; nohup setsid $BIN -m $Q --host 127.0.0.1 --port 8083 -c 8192 -ngl 99 -fa on --parallel 2 --jinja > $LG/fast_server.log 2>&1 < /dev/null &
fi
# 4. GLM
if [ -z "$WAIT_MODEL" ] && ! up 8081; then
  M=$N/glm53/GLM-5.3-UD-Q4_K_XL-00001-of-00011.gguf; log "GLM :8081"
  nohup setsid $BIN -m $M --host 127.0.0.1 --port 8081 -c 16384 -t 24 -tb 24 -ngl 38 --n-cpu-moe 999 -fa on --parallel 1 --jinja --temp 1.0 --top-p 0.95 --min-p 0.01 > $LG/glm_server.log 2>&1 < /dev/null &
fi
# 5. шлюз (qs6): быстрый тир + GLM, память, душа
if ! pgrep -f "glm53/gateway.py" >/dev/null; then
  log "gateway :8082"; cd $C/glm53
  PYTHONPATH=$C NOX_UPSTREAM=http://127.0.0.1:8081 NOX_FAST_UPSTREAM=http://127.0.0.1:8083 NOX_TWO_STAGE=1 nohup setsid python3 gateway.py > $LG/gateway.log 2>&1 < /dev/null &
fi
# 6. веб
pgrep -f "/root/nox/web_server.py" >/dev/null || { [ -d $N/web ] && { cp $C/s1web/web_server.py $N/web_server.py; nohup setsid python3 $N/web_server.py > $LG/web_server.log 2>&1 < /dev/null & log "web :8091"; }; }
# 7. голос
P=$(find $DL/hf/piper_ru -name "*.onnx" -path "*ru*" | head -1); E=$(find $DL/hf/piper_ru -name "*.onnx" -path "*es*" | head -1)
export NOX_PIPER_MODEL_RU=$P NOX_PIPER_MODEL_ES=$E NOX_STT_MODEL=$DL/hf/whisper_small NOX_TTS_BACKENDS=piper,xtts NOX_STT_DEVICE=cpu
export NOX_SMART_TURN_MODEL=$(find $DL/hf/smart_turn -name "*.onnx" | head -1)
bash $C/voice/start_voice.sh all 2>&1 | tail -4
sleep 8; for p in 8083 8081 8082 8091 8093 8094; do up $p && echo "UP $p" || echo "down $p"; done | tr '\n' ' '; echo
