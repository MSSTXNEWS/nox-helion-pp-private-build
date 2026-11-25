#!/bin/bash
export PATH=/workspace/nox/tools/node/bin:$PATH
S=/workspace/nox/svc; L=$S/logs; D=$S/data; mkdir -p $L $D; cd $S
H=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
curl -fsSL $H/d_svc_reg.py -o /workspace/nox/svc/d_svc_reg.py
free(){ df -BG /workspace | tail -1 | awk '{gsub("G","",$4);print $4}'; }
usedports(){ ss -ltn | awk '{print $4}' | sed 's/.*://' ; }
PF=$S/d_ports.txt; touch $PF
pick(){ n=$1; g=$(grep "^$n " $PF | cut -d' ' -f2); [ -n "$g" ] && { echo $g; return; }; for p in $(seq 18200 18260); do if ! usedports | grep -qx $p && ! grep -q " $p\$" $PF; then echo "$n $p" >> $PF; echo $p; return; fi; done; }
STARTS=$S/start_d.sh; [ -f $STARTS ] || { echo '#!/bin/bash
# старт сервисов исполнителя D (идемпотентно, 127.0.0.1)
S=/workspace/nox/svc; L=$S/logs; D=$S/data; export PATH=/workspace/nox/tools/node/bin:$PATH
up(){ (echo > /dev/tcp/127.0.0.1/$1) 2>/dev/null; }' > $STARTS; }
addstart(){ grep -q "#$1\$" $STARTS || echo "$2 #$1" >> $STARTS; }
log(){ echo "[$(date +%H:%M)] $*" | tee -a $S/d_install.log; }
gh_get(){ curl -sL -m 30 https://api.github.com/repos/$1/releases/latest | python3 -c "import sys,json,re;d=json.load(sys.stdin);print(next((a['browser_download_url'] for a in d['assets'] if re.search('$2',a['name'])),''))"; }
reg(){ python3 $S/d_svc_reg.py "$@"; }
wait_up(){ for i in $(seq 1 40); do (echo > /dev/tcp/127.0.0.1/$1) 2>/dev/null && return 0; sleep 3; done; return 1; }
[ $(free) -lt 20 ] && { log "STOP disk $(free)G"; exit; }
# ---- Glance
if [ ! -x glance/glance ]; then mkdir -p glance; u=$(gh_get glanceapp/glance 'linux-amd64.tar.gz$'); curl -fsSL "$u" | tar xz -C glance 2>&1|tail -1; fi
if [ -x glance/glance ]; then P=$(pick glance); cat > glance/glance.yml <<Y
server:
  host: 127.0.0.1
  port: $P
  base-url: /svc/glance
theme:
  background-color: 240 8 9
  primary-color: 12 80 60
pages:
  - name: NOX
    columns:
      - size: small
        widgets:
          - type: clock
          - type: calendar
          - type: weather
            location: Sevastopol, Russia
            units: metric
      - size: full
        widgets:
          - type: rss
            title: Новости
            feeds:
              - url: https://habr.com/ru/rss/articles/
                title: Habr
              - url: https://feeds.bbci.co.uk/news/world/rss.xml
                title: BBC
          - type: hacker-news
      - size: small
        widgets:
          - type: markets
            markets:
              - symbol: BTC-USD
                name: Bitcoin
              - symbol: EURUSD=X
                name: EUR/USD
Y
addstart glance "up $P || (cd \$S/glance && nohup setsid ./glance --config glance.yml >\$L/glance.log 2>&1 &)"
(cd glance && nohup setsid ./glance --config glance.yml >$L/glance.log 2>&1 &); wait_up $P && reg glance $P base Glance "Лента: погода, RSS, рынки" && log "OK glance $P" || log "FAIL glance не стартовал"; else log "FAIL glance не скачан"; fi
# ---- Memos
if [ ! -x memos/memos ]; then mkdir -p memos; u=$(gh_get usememos/memos 'linux_amd64.tar.gz$'); curl -fsSL "$u" | tar xz -C memos 2>&1|tail -1; fi
if [ -x memos/memos ]; then P=$(pick memos); mkdir -p $D/memos; addstart memos "up $P || (cd \$S/memos && nohup setsid ./memos --addr 127.0.0.1 --port $P --data \$D/memos --mode prod >\$L/memos.log 2>&1 &)"
(cd memos && nohup setsid ./memos --addr 127.0.0.1 --port $P --data $D/memos --mode prod >$L/memos.log 2>&1 &); wait_up $P && reg memos $P strip Memos "Заметки (Go, SQLite)" && log "OK memos $P" || log "FAIL memos не стартовал: $(tail -2 $L/memos.log|tr '\n' ' ')"; else log "FAIL memos не скачан"; fi
# ---- Radicale
if [ ! -x radicale/venv/bin/python ]; then mkdir -p radicale; python3 -m venv radicale/venv && radicale/venv/bin/pip -q install radicale 2>&1|tail -1; fi
if [ -x radicale/venv/bin/radicale ]; then P=$(pick radicale); mkdir -p $D/radicale; cat > radicale/config <<Y
[server]
hosts = 127.0.0.1:$P
[auth]
type = none
[storage]
filesystem_folder = $D/radicale
Y
addstart radicale "up $P || (nohup setsid \$S/radicale/venv/bin/radicale --config \$S/radicale/config >\$L/radicale.log 2>&1 &)"
(nohup setsid radicale/venv/bin/radicale --config radicale/config >$L/radicale.log 2>&1 &); wait_up $P && reg radicale $P strip Radicale "Календарь и контакты CalDAV/CardDAV, без пароля" && log "OK radicale $P" || log "FAIL radicale"; else log "FAIL radicale pip"; fi
# ---- Beszel
if [ ! -x beszel/beszel ]; then mkdir -p beszel; u=$(gh_get henrygd/beszel '^beszel_linux_amd64.tar.gz$'); curl -fsSL "$u" | tar xz -C beszel 2>&1|tail -1; fi
if [ -x beszel/beszel ]; then P=$(pick beszel); addstart beszel "up $P || (cd \$S/beszel && nohup setsid ./beszel serve --http 127.0.0.1:$P >\$L/beszel.log 2>&1 &)"
(cd beszel && nohup setsid ./beszel serve --http 127.0.0.1:$P >$L/beszel.log 2>&1 &); wait_up $P && reg beszel $P strip Beszel "Мониторинг сервера (hub); первый вход создаёт админа" && log "OK beszel $P" || log "FAIL beszel"; else log "FAIL beszel не скачан"; fi
# ---- Actual
if [ ! -d actual/node_modules/@actual-app/sync-server ]; then mkdir -p actual; (cd actual && [ -f package.json ] || npm init -y >/dev/null; npm i --no-audit --no-fund @actual-app/sync-server 2>&1|tail -1); fi
AB=$(ls actual/node_modules/.bin 2>/dev/null | grep -i actual | head -1)
if [ -n "$AB" ]; then P=$(pick actual); mkdir -p $D/actual; addstart actual "up $P || (cd \$S/actual && ACTUAL_PORT=$P ACTUAL_HOSTNAME=127.0.0.1 ACTUAL_DATA_DIR=\$D/actual nohup setsid node_modules/.bin/$AB >\$L/actual.log 2>&1 &)"
(cd actual && ACTUAL_PORT=$P ACTUAL_HOSTNAME=127.0.0.1 ACTUAL_DATA_DIR=$D/actual nohup setsid node_modules/.bin/$AB >$L/actual.log 2>&1 &); wait_up $P && reg actual $P strip "Actual Budget" "Бюджет; при первом входе задать пароль" && log "OK actual $P" || log "FAIL actual: $(tail -2 $L/actual.log|tr '\n' ' ')"; else log "FAIL actual нет bin"; fi
# ---- Uptime Kuma
if [ ! -f kuma/server/server.js ]; then T=$(curl -sL https://api.github.com/repos/louislam/uptime-kuma/releases/latest | python3 -c "import sys,json;print(json.load(sys.stdin)['tag_name'])"); git clone --depth 1 --branch $T https://github.com/louislam/uptime-kuma.git kuma 2>&1|tail -1; (cd kuma && npm ci --omit dev --no-audit --no-fund 2>&1|tail -1; npm run download-dist 2>&1|tail -1); fi
if [ -f kuma/dist/index.html ]; then P=$(pick kuma); mkdir -p $D/kuma; addstart kuma "up $P || (cd \$S/kuma && UPTIME_KUMA_HOST=127.0.0.1 UPTIME_KUMA_PORT=$P DATA_DIR=\$D/kuma/ nohup setsid node server/server.js >\$L/kuma.log 2>&1 &)"
(cd kuma && UPTIME_KUMA_HOST=127.0.0.1 UPTIME_KUMA_PORT=$P DATA_DIR=$D/kuma/ nohup setsid node server/server.js >$L/kuma.log 2>&1 &); wait_up $P && reg kuma $P strip "Uptime Kuma" "Мониторинг доступности; при первом входе создать админа" && log "OK kuma $P" || log "FAIL kuma: $(tail -3 $L/kuma.log|tr '\n' ' ')"; else log "FAIL kuma сборка"; fi
# ---- Stirling-PDF (jar + JRE)
if [ $(free) -ge 20 ]; then
 if [ ! -x jre/bin/java ]; then mkdir -p jre; curl -fsSL "https://api.adoptium.net/v3/binary/latest/21/ga/linux/x64/jre/hotspot/normal/eclipse" | tar xz -C jre --strip-components=1 2>&1|tail -1; fi
 if [ ! -f stirling/Stirling-PDF.jar ]; then mkdir -p stirling; u=$(gh_get Stirling-Tools/Stirling-PDF '^Stirling-PDF.jar$'); curl -fsSL "$u" -o stirling/Stirling-PDF.jar; fi
 if [ -x jre/bin/java ] && [ -s stirling/Stirling-PDF.jar ]; then P=$(pick stirling); CMD="cd \$S/stirling && SERVER_ADDRESS=127.0.0.1 SERVER_PORT=$P SERVER_SERVLET_CONTEXT_PATH=/svc/stirling DOCKER_ENABLE_SECURITY=false SECURITY_ENABLELOGIN=false nohup setsid \$S/jre/bin/java -Xmx1g -jar Stirling-PDF.jar >\$L/stirling.log 2>&1 &"
 addstart stirling "up $P || ($CMD)"
 (eval "$(echo "$CMD" | sed "s#\$S#$S#g; s#\$L#$L#g")"); for i in $(seq 1 60); do (echo > /dev/tcp/127.0.0.1/$P) 2>/dev/null && break; sleep 3; done; (echo > /dev/tcp/127.0.0.1/$P) 2>/dev/null && reg stirling $P base Stirling-PDF "PDF-инструменты (jar, Java 21 JRE в svc/jre)" && log "OK stirling $P" || log "FAIL stirling: $(tail -3 $L/stirling.log|tr '\n' ' ')"; else log "FAIL stirling не скачан"; fi
else log "SKIP stirling диск"; fi
# ---- code-server
if [ $(free) -ge 20 ]; then
 if [ ! -x code-server/bin/code-server ]; then mkdir -p code-server; u=$(gh_get coder/code-server 'linux-amd64.tar.gz$'); curl -fsSL "$u" | tar xz -C code-server --strip-components=1 2>&1|tail -1; fi
 if [ -x code-server/bin/code-server ]; then P=$(pick codeserver); mkdir -p $D/code-server; addstart codeserver "up $P || (nohup setsid \$S/code-server/bin/code-server --bind-addr 127.0.0.1:$P --auth none --user-data-dir \$D/code-server /workspace/nox/web >\$L/code-server.log 2>&1 &)"
 (nohup setsid code-server/bin/code-server --bind-addr 127.0.0.1:$P --auth none --user-data-dir $D/code-server /workspace/nox/web >$L/code-server.log 2>&1 &); wait_up $P && reg codeserver $P strip "code-server" "VS Code в браузере, корень /workspace/nox/web" && log "OK code-server $P" || log "FAIL code-server"; else log "FAIL code-server не скачан"; fi
else log "SKIP code-server диск"; fi
# ---- Podcastfy + WhisperLive (python 3.11 через uv)
for pkgsvc in podcastfy whisperlive; do
 if [ $(free) -lt 22 ]; then log "SKIP $pkgsvc диск $(free)G"; continue; fi
 if [ ! -x $pkgsvc/venv/bin/python ]; then mkdir -p $pkgsvc; uv venv --python 3.11 $pkgsvc/venv 2>&1|tail -1; fi
 if [ $pkgsvc = podcastfy ]; then uv pip install --python podcastfy/venv/bin/python podcastfy uvicorn 2>&1|tail -2; podcastfy/venv/bin/python -c "import podcastfy;print('podcastfy import ok')" 2>&1|tail -1
   M=$(podcastfy/venv/bin/python -c "import importlib.util as u;print('podcastfy.api.fast_app' if u.find_spec('podcastfy.api.fast_app') else '')" 2>/dev/null)
   if [ -n "$M" ]; then P=$(pick podcastfy); addstart podcastfy "up $P || (cd \$S/podcastfy && nohup setsid venv/bin/python -m uvicorn $M:app --host 127.0.0.1 --port $P >\$L/podcastfy.log 2>&1 &)"
   (cd podcastfy && nohup setsid venv/bin/python -m uvicorn $M:app --host 127.0.0.1 --port $P >$L/podcastfy.log 2>&1 &); wait_up $P && reg podcastfy $P strip Podcastfy "API подкастов (нужны ключи LLM/TTS в env)" && log "OK podcastfy $P" || log "FAIL podcastfy api: $(tail -2 $L/podcastfy.log|tr '\n' ' ')"
   else log "PARTIAL podcastfy: библиотека поставлена, HTTP-API в пакете не найден"; fi
 else uv pip install --python whisperlive/venv/bin/python whisper-live 2>&1|tail -2
   if whisperlive/venv/bin/python -c "import whisper_live" 2>/dev/null; then P=$(pick whisperlive); echo "from whisper_live.server import TranscriptionServer
import sys
TranscriptionServer().run('127.0.0.1', port=int(sys.argv[1]), backend='faster_whisper')" > whisperlive/run_server.py
   addstart whisperlive "up $P || (cd \$S/whisperlive && nohup setsid venv/bin/python run_server.py $P >\$L/whisperlive.log 2>&1 &)"
   (cd whisperlive && nohup setsid venv/bin/python run_server.py $P >$L/whisperlive.log 2>&1 &); wait_up $P && reg whisperlive $P strip WhisperLive "WebSocket живых субтитров (faster-whisper)" && log "OK whisperlive $P" || log "FAIL whisperlive: $(tail -3 $L/whisperlive.log|tr '\n' ' ')"
   else log "FAIL whisperlive pip"; fi; fi
done
grep -q start_d.sh $S/start_all.sh || { cp $S/start_all.sh $S/start_all.sh.bak_d_1; sed -i 's#^exit 0#[ -x $S/start_d.sh ] \&\& bash $S/start_d.sh\nexit 0#' $S/start_all.sh; }
log "ALLDONE free $(free)G"
