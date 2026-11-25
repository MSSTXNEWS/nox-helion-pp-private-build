#!/bin/bash
S=/workspace/nox/svc; L=$S/logs; D=$S/data; cd $S
log(){ echo "[$(date +%H:%M)] $*" | tee -a $S/d_install.log; }
free(){ df -BG /workspace | tail -1 | awk '{gsub("G","",$4);print $4}'; }
reg(){ python3 $S/d_svc_reg.py "$@"; }
wait_up(){ for i in $(seq 1 60); do (echo > /dev/tcp/127.0.0.1/$1) 2>/dev/null && return 0; sleep 3; done; return 1; }
# memos
sed -i 's/ --mode prod//' start_d.sh
P=$(grep '^memos ' d_ports.txt | cut -d' ' -f2); (cd memos && nohup setsid ./memos --addr 127.0.0.1 --port $P --data $D/memos >$L/memos.log 2>&1 &); wait_up $P && reg memos $P strip Memos "Заметки (Go, SQLite)" && log "OK memos $P" || log "FAIL memos: $(tail -2 $L/memos.log|tr '\n' ' ')"
# stirling: Java 25
rm -rf jre25; mkdir -p jre25; curl -fsSL "https://api.adoptium.net/v3/binary/latest/25/ga/linux/x64/jre/hotspot/normal/eclipse" | tar xz -C jre25 --strip-components=1 2>&1|tail -1
if [ -x jre25/bin/java ]; then P=$(grep '^stirling ' d_ports.txt | cut -d' ' -f2)
 sed -i 's#\$S/jre/bin/java#$S/jre25/bin/java#' start_d.sh
 (cd stirling && SERVER_ADDRESS=127.0.0.1 SERVER_PORT=$P SERVER_SERVLET_CONTEXT_PATH=/svc/stirling DOCKER_ENABLE_SECURITY=false SECURITY_ENABLELOGIN=false nohup setsid $S/jre25/bin/java -Xmx1g -jar Stirling-PDF.jar >$L/stirling.log 2>&1 &)
 for i in $(seq 1 80); do (echo > /dev/tcp/127.0.0.1/$P) 2>/dev/null && break; sleep 3; done
 (echo > /dev/tcp/127.0.0.1/$P) 2>/dev/null && reg stirling $P base Stirling-PDF "PDF-инструменты (jar, Java 25 JRE в svc/jre25)" && log "OK stirling $P" || log "FAIL stirling: $(grep -m2 -E 'Error|Exception' $L/stirling.log|tr '\n' ' '|cut -c1-300)"
else log "FAIL stirling jre25"; fi
# podcastfy: fastapi
uv pip install --python podcastfy/venv/bin/python fastapi uvicorn python-multipart 2>&1|tail -1
P=$(grep '^podcastfy ' d_ports.txt | cut -d' ' -f2); (cd podcastfy && nohup setsid venv/bin/python -m uvicorn podcastfy.api.fast_app:app --host 127.0.0.1 --port $P >$L/podcastfy.log 2>&1 &); wait_up $P && reg podcastfy $P strip Podcastfy "API подкастов (нужны ключи LLM/TTS в env)" && log "OK podcastfy $P" || log "FAIL podcastfy: $(tail -3 $L/podcastfy.log|tr '\n' ' '|cut -c1-300)"
# whisperlive: dry-run, затем установка при запасе
mkdir -p whisperlive; [ -x whisperlive/venv/bin/python ] || uv venv --python 3.11 whisperlive/venv 2>&1|tail -1
uv pip install --python whisperlive/venv/bin/python --dry-run whisper-live 2>&1 | tail -40 > whisperlive/dry.txt; tail -15 whisperlive/dry.txt | cut -c1-200
if grep -qiE "error|No solution|failed" whisperlive/dry.txt; then log "FAIL whisperlive pip (resolve): $(grep -iE 'error|because|failed' whisperlive/dry.txt|head -2|tr '\n' ' '|cut -c1-300)"
elif [ $(free) -ge 24 ]; then uv pip install --python whisperlive/venv/bin/python whisper-live 2>&1|tail -3
 if whisperlive/venv/bin/python -c "import whisper_live" 2>/dev/null; then P=$(pick 2>/dev/null); P=18208
  echo "from whisper_live.server import TranscriptionServer
import sys
TranscriptionServer().run('127.0.0.1', port=int(sys.argv[1]), backend='faster_whisper')" > whisperlive/run_server.py
  grep -q whisperlive start_d.sh || echo "up $P || (cd \$S/whisperlive && nohup setsid venv/bin/python run_server.py $P >\$L/whisperlive.log 2>&1 &) #whisperlive" >> start_d.sh
  (cd whisperlive && nohup setsid venv/bin/python run_server.py $P >$L/whisperlive.log 2>&1 &); wait_up $P && reg whisperlive $P strip WhisperLive "WebSocket живых субтитров (faster-whisper)" && log "OK whisperlive $P" || log "FAIL whisperlive: $(tail -3 $L/whisperlive.log|tr '\n' ' '|cut -c1-300)"
 else log "FAIL whisperlive import"; fi
else log "SKIP whisperlive диск $(free)G"; fi
log "FIXDONE free $(free)G"
