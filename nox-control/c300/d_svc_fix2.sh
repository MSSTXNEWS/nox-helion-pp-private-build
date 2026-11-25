#!/bin/bash
S=/workspace/nox/svc; L=$S/logs; cd $S
log(){ echo "[$(date +%H:%M)] $*" | tee -a $S/d_install.log; }
free(){ df -BG /workspace | tail -1 | awk '{gsub("G","",$4);print $4}'; }
reg(){ python3 $S/d_svc_reg.py "$@"; }
wait_up(){ for i in $(seq 1 60); do (echo > /dev/tcp/127.0.0.1/$1) 2>/dev/null && return 0; sleep 3; done; return 1; }
V=podcastfy/venv/bin/python
for i in 1 2 3 4 5 6; do m=$($V -c "import podcastfy.api.fast_app" 2>&1 | grep -oP "No module named '\K[^'.]+" | head -1); [ -z "$m" ] && break; echo "podcastfy dep $m"; uv pip install --python $V $m 2>&1|tail -1; done
$V -c "import podcastfy.api.fast_app" 2>&1 | tail -2 | cut -c1-200
P=$(grep '^podcastfy ' d_ports.txt | cut -d' ' -f2); (cd podcastfy && nohup setsid venv/bin/python -m uvicorn podcastfy.api.fast_app:app --host 127.0.0.1 --port $P >$L/podcastfy.log 2>&1 &); wait_up $P && reg podcastfy $P strip Podcastfy "API подкастов (нужны ключи LLM/TTS в env)" && log "OK podcastfy $P" || log "FAIL podcastfy: $(tail -2 $L/podcastfy.log|tr '\n' ' '|cut -c1-250)"
# whisperlive без pyaudio
W=whisperlive/venv/bin/python
uv pip install --python $W whisper-live --no-deps 2>&1|tail -1
uv pip install --python $W faster-whisper websockets websocket-client numpy scipy onnxruntime requests tqdm av soundfile 2>&1|tail -1
for i in 1 2 3 4 5 6 7 8; do [ $(free) -lt 20 ] && { log "STOP whisperlive диск"; break; }; m=$($W -c "from whisper_live.server import TranscriptionServer" 2>&1 | grep -oP "No module named '\K[^'.]+" | head -1); [ -z "$m" ] && break; echo "wl dep $m"; [ $m = torch ] && { log "SKIP torch для whisperlive нужен"; break; }; uv pip install --python $W $m 2>&1|tail -1; done
if $W -c "from whisper_live.server import TranscriptionServer" 2>/dev/null; then P=18208
 echo "from whisper_live.server import TranscriptionServer
import sys
TranscriptionServer().run('127.0.0.1', port=int(sys.argv[1]), backend='faster_whisper')" > whisperlive/run_server.py
 grep -q whisperlive start_d.sh || echo "up $P || (cd \$S/whisperlive && nohup setsid venv/bin/python run_server.py $P >\$L/whisperlive.log 2>&1 &) #whisperlive" >> start_d.sh
 (cd whisperlive && nohup setsid venv/bin/python run_server.py $P >$L/whisperlive.log 2>&1 &); wait_up $P && reg whisperlive $P strip WhisperLive "WebSocket живых субтитров (faster-whisper, pyaudio не ставился)" && log "OK whisperlive $P" || log "FAIL whisperlive: $(tail -3 $L/whisperlive.log|tr '\n' ' '|cut -c1-300)"
else log "FAIL whisperlive import: $($W -c 'from whisper_live.server import TranscriptionServer' 2>&1|tail -1|cut -c1-200)"; fi
log "FIX2DONE free $(free)G"
