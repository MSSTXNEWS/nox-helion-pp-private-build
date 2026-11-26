echo "K1: k1_gchk"
U=$(curl -s -m 3 http://127.0.0.1:20999/quicktunnel | grep -oE "\"hostname\":\"[^\"]+\"" | cut -d\" -f4)
echo "alive=$([ -n "$U" ] && echo yes || echo no) pub_auth=$(curl -s -o /dev/null -m 15 -w %{http_code} -u owner:$(cat /workspace/nox/state/owner_gate/pass) https://$U/web/chat-dc.html)"
