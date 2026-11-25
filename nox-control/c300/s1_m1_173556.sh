S=/workspace/nox/web/site
cd $S
[ -f x.txt ] && cp -p x.txt x.txt.bak_s1_$(date +%H%M%S)
base64 -d > x.txt <<'S1EOF'
eAo=
S1EOF
echo OK x.txt $(wc -c <x.txt)
curl -s -m60 -X POST http://127.0.0.1:8091/api/chat -H 'Content-Type: application/json' -d '{"model":"nox-helion:latest","stream":true,"nox_mode":"fast","conversation_id":"s1-meta","messages":[{"role":"user","content":"/статус"}]}' | head -c 1500; echo; echo ----
curl -s -m60 -X POST http://127.0.0.1:8091/api/turn -H 'Content-Type: application/json' -d '{"message":"/статус","conversation_id":"s1-meta"}' | head -c 800
