echo "C300: d_p1"
grep -E "whisperlive|FIX|OK|FAIL" /workspace/nox/svc/d_install.log | tail -4 | cut -c1-200
curl -s -m 5 http://127.0.0.1:8095/ -o /dev/null; for n in glance memos radicale beszel actual kuma stirling codeserver podcastfy whisperlive; do p=$(grep "^$n " /workspace/nox/svc/d_ports.txt | cut -d' ' -f2); [ $n = glance ] && p=18200; (echo > /dev/tcp/127.0.0.1/$p) 2>/dev/null && echo "UP $n $p" || echo "DOWN $n $p"; done
ls /workspace/nox/web/site/vendor/vidstack /workspace/nox/web/site/vendor/vidstack/player 2>&1 | head -12; df -BG /workspace|tail -1
