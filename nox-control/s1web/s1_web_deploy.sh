#!/bin/bash
# S1: скачать последнюю веб-сборку из ветки nox-web-dist, проверить sha256, распаковать в /root/nox/web, запустить веб-сервер 127.0.0.1:8091
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build
mkdir -p /root/nox/web_dl /root/nox/web /root/nox/logs; cd /root/nox/web_dl; rm -f nox-web.part* pkg.tar.xz
curl -fsSL $R/nox-web-dist/SHA256 -o SHA256 || { echo "no SHA256"; exit 1; }
for i in $(seq -w 0 20); do curl -fsSL -o nox-web.part$i $R/nox-web-dist/nox-web.part$i || { rm -f nox-web.part$i; break; }; done
ls nox-web.part* | wc -l; cat nox-web.part* > pkg.tar.xz; [ "$(sha256sum pkg.tar.xz | cut -d' ' -f1)" = "$(cat SHA256)" ] && echo "SHA OK" || { echo "SHA MISMATCH"; exit 1; }
rm -rf /root/nox/web.new && mkdir /root/nox/web.new && tar -C /root/nox/web.new -xJf pkg.tar.xz && rm -rf /root/nox/web.old && { [ -d /root/nox/web ] && mv /root/nox/web /root/nox/web.old; mv /root/nox/web.new /root/nox/web; }
curl -fsSL $R/main/nox-control/s1web/web_server.py -o /root/nox/web_server.py
pkill -f "/root/nox/web_server.py"; sleep 1
nohup setsid python3 /root/nox/web_server.py > /root/nox/logs/web_server.log 2>&1 < /dev/null &
sleep 2; curl -s -o /dev/null -w "web http=%{http_code}\n" http://127.0.0.1:8091/web/chat.html; ls /root/nox/web | wc -l
