curl -s -m 5 localhost:8091/img/health | head -c 1500; echo
for b in '{}' '{"prompt":"x"}' '{"probe":true}'; do curl -s -m 5 -o /tmp/o -w "%{http_code} " -X POST localhost:8091/img/generate -H 'content-type: application/json' -d "$b"; head -c 150 /tmp/o; echo; done
