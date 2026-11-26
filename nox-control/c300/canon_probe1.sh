#!/bin/bash
echo "C300: canon_probe1"
N=/workspace/nox
f(){ # label pattern...
  l=$1; shift; r=$(find $N -maxdepth 4 \( -path '*/venv' -o -path '*/node_modules' -o -path '*/.git' -o -path '*/ckpt*' -o -path '*/models' \) -prune -o \( "$@" \) -print 2>/dev/null | head -3 | tr '\n' ' '); echo "$l: ${r:-NONE}"; }
echo "== host"; df -h /workspace | tail -1; nvidia-smi --query-gpu=memory.used,memory.total,temperature.gpu --format=csv,noheader 2>&1 | head -2
echo "== ch1 body"
supervisorctl status 2>&1 | awk '{print $1,$2}' | head -40
ls /etc/systemd/system 2>/dev/null | grep -i nox | head -3
f watchdog -iname '*watchdog*' -o -iname '*storozh*' -o -iname 'guard*.sh' -o -iname '*sentinel*'
f backup_soul -iname '*soul*backup*' -o -iname 'backup_soul*' -o -iname '*dusha*backup*'
ls -d $N/archive/gb10_final 2>&1 | head -1; ls $N/archive 2>/dev/null | head -5
ls $N/backup* $N/backups 2>/dev/null | tail -4
which age 2>&1 | head -1
echo "== ch2 live"
f board -iname 'board*.py' -o -iname 'board*.json'
f dispatcher -iname '*dispatch*.py'
f arq_redis -iname '*arq*' -o -iname 'redis*.conf'
(redis-cli ping 2>&1 | head -1); pgrep -af 'redis-server|arq' | head -2 | cut -c1-100
f fillers -iname '*filler*'
f action_receipt -iname '*receipt*'
f eventbus -iname '*bus*.py' -o -iname 'events*.db' -o -iname 'events*.sqlite'
echo "== ch3 modes"
f mode -iname '*mode*.py' -o -iname 'board_mode*'
f cvector -iname '*.gguf' -path '*vector*' -o -iname '*control_vec*' -o -iname '*cvector*' -o -iname '*repeng*'
echo "== ch4 feel"
f sensorium -iname '*sensor*' -o -iname '*sensorium*'
f neurochem -iname '*neurochem*' -o -iname '*chem*panel*' -o -iname 'pad_*.py' -o -iname '*emotion*.py'
f drives -iname '*drive*.py' -o -iname '*vlecheni*'
ls $N/models 2>/dev/null | grep -iE 'cedr|rubert|dusha|emotion' | head
echo "== ch5 mem"
f s03 -iname 's03*' -o -iname '*s03*.db' -o -iname '*s03*.py'
f memory_m -iname 'm[0-7]_*' -o -iname 'memory*.py'
f graphiti -iname '*graphiti*' -o -iname '*zep*'
f mem0 -iname '*mem0*'
f letta -iname '*letta*' -o -iname '*sleep*.py' -o -iname 'dream*'
find / -maxdepth 6 \( -iname 'bge-m3*' -o -iname 'bge-reranker*' \) -not -path '/proc/*' 2>/dev/null | head -3
python3 -c "import sqlite_vec" 2>&1 | tail -1; $N/venv/bin/python -c "import sqlite_vec;print('sqlite_vec ok')" 2>&1 | tail -1
echo "== ch6 mind"
f workspace -iname '*workspace*.py' -o -iname 'gwt*' -o -iname '*council*.py' -o -iname '*coreid*'
f self_now -iname '*ya_seychas*' -o -iname '*self_now*' -o -iname '*i_now*'
f refine -iname '*refine*' -o -iname '*reflex*'
f calib -iname '*calib*' -o -iname '*ece*'
f tom -iname '*tom*.py' -o -iname '*mentaliz*'
echo "== ch7 time"
f tick -iname '*tick*.py' -o -iname '*tick*.sh' -o -iname 'life*.py'
f morning -iname '*morning*' -o -iname '*evening*' -o -iname '*utro*'
f initiative -iname '*initiat*'
f quiet -iname '*quiet*'
echo "== ch8 char"
f passport -iname 'passport*.json'
f birth -iname 'birth_ritual*' -o -iname '*genesis*ledger*' -o -iname '*genesis*'
f stages -iname '*stage*exam*' -o -iname '*growth*stage*'
grep -rls 'born_at' $N --include=*.json --include=*.py 2>/dev/null | head -3
echo "== ch9 hunter"
f worms -iname '*worm*.py' -o -iname '*worm*.sh'
f catalog -iname '*catalog*.json*' -o -iname '*katalog*'
f absorb -iname '*absorb*' -o -iname '*poglosh*'
f hunger -iname '*hunger*' -o -iname '*golod*'
f unknownmap -iname '*unknownmap*' -o -iname '*unknown_map*'
echo "== ch10 train"
f ready_bulk -iname '*ready_bulk*'
f dpo -iname 'train_dpo.py' -o -iname 'build_dpo.py'
f hold400 -iname '*hold*400*' -o -iname 'hold*.jsonl'
f vectors -iname '*persona*vector*'
f huihui -iname '*huihui*'
echo "== ch11 voice"
f stt -iname '*t-one*' -o -iname '*tone*stt*' -o -iname '*gigaam*' -o -iname '*parakeet*'
f tts -iname '*qwen3*tts*' -o -iname '*cosyvoice*' -o -iname '*tts*.py'
f pipecat -iname '*pipecat*' -o -iname '*silero*'
f voice_anchor -iname '*voice*anchor*' -o -iname '*voice*passport*'
echo "== ch12 create"
f draw -iname '*draw*.py' -o -iname 'imgsvc*'
f vlm -iname '*qwen3*vl*' -o -iname '*vlm*.py'
f editor -iname '*editor*.html' -o -iname '*inpaint*'
f video -iname '*wan2*' -o -iname '*ltx*'
f openhands -iname '*openhands*' -o -iname '*sandbox*.py'
f chroma -iname '*chroma*'
echo "== ch13 safety"
f inject -iname '*inject*' -o -iname '*agentdojo*'
f stop -iname 'STOP*' -o -iname '*stop_watch*'
f matrix -iname '*autonomy*matrix*' -o -iname '*consent*'
f ledger -iname '*ledger*'
echo "== ch14/15 exam"
f weekly_exam -iname '*weekly*exam*' -o -iname '*zhivost*' -o -iname '*liveness*' -o -iname '*exam*.py'
f twin -iname '*twin*' -o -iname '*dvoynik*'
f forge -iname '*forge*'
echo "== cron(read only)"
crontab -l 2>/dev/null | grep -v '^#' | awk '{print $6,$7,$8}' | cut -c1-60 | head -30
echo "== ports"
ss -ltn 2>/dev/null | awk 'NR>1{print $4}' | sed 's/.*://' | sort -n | uniq | tr '\n' ' '
