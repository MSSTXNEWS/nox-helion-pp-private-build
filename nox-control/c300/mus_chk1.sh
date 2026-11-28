echo "K1: mus_chk1"
supervisorctl status 2>/dev/null | grep -iE "music|ace|audio" | awk '{print "sv",$1,$2}'
for port in 8095 8096 8097 8188 7865 8020 18230; do c=$(curl -s -o /dev/null -m 3 -w %{http_code} http://127.0.0.1:$port/ 2>/dev/null); [ "$c" != 000 ] && echo "port $port $c"; done
ss -ltn | awk '{print $4}' | grep -oE ':[0-9]+$' | sort -u | tr '\n' ' '; echo
echo "inspector_top: $(ls -t /workspace/nox/state/inspector/hints 2>/dev/null | head -5 | sed 's/\.json//' | cut -c1-24 | tr '\n' ' ')"
echo END
