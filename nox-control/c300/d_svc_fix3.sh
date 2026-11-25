#!/bin/bash
S=/workspace/nox/svc; L=$S/logs; cd $S; W=whisperlive/venv/bin/python
log(){ echo "[$(date +%H:%M)] $*" | tee -a $S/d_install.log; }
wait_up(){ for i in $(seq 1 80); do (echo > /dev/tcp/127.0.0.1/$1) 2>/dev/null && return 0; sleep 3; done; return 1; }
uv pip install --python $W torch torchaudio --index-url https://download.pytorch.org/whl/cpu 2>&1|tail -1
for i in 1 2 3 4 5 6; do m=$($W -c "from whisper_live.server import TranscriptionServer" 2>&1 | grep -oP "No module named '\K[^'.]+" | head -1); [ -z "$m" ] && break; echo "dep $m"; uv pip install --python $W $m 2>&1|tail -1; done
if $W -c "from whisper_live.server import TranscriptionServer" 2>/dev/null; then P=18209
 echo "from whisper_live.server import TranscriptionServer
import sys
TranscriptionServer().run('127.0.0.1', port=int(sys.argv[1]), backend='faster_whisper')" > whisperlive/run_server.py
 sed -i '/#whisperlive$/d' start_d.sh; echo "up $P || (cd \$S/whisperlive && nohup setsid venv/bin/python run_server.py $P >\$L/whisperlive.log 2>&1 &) #whisperlive" >> start_d.sh
 (cd whisperlive && nohup setsid venv/bin/python run_server.py $P >$L/whisperlive.log 2>&1 &); wait_up $P && python3 d_svc_reg.py whisperlive $P strip WhisperLive "WebSocket живых субтитров (faster-whisper, CPU torch)" && log "OK whisperlive $P" || log "FAIL whisperlive: $(tail -3 $L/whisperlive.log|tr '\n' ' '|cut -c1-300)"
else log "FAIL whisperlive import: $($W -c 'from whisper_live.server import TranscriptionServer' 2>&1|tail -1|cut -c1-200)"; fi
echo "reg:"; python3 -c "import json;d=json.load(open('/workspace/nox/web/pkg/server/svc_registry.json'));print(sorted(d))"
