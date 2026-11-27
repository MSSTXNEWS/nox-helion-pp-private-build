echo "K1: ln_f1"
export RUNNER_TRACKING_ID=""
S=/workspace/nox/tools/searxng_conf/settings.yml
B=$S.bak_launch_$(date +%s); cp -a $S $B; echo backup ok
grep -q "launch_engines" $S || cat >> $S <<'Y'
# launch_engines: DDG капча и google cse заблокированы, включаем рабочие
engines:
  - name: duckduckgo
    disabled: true
  - name: google cse
    disabled: true
  - name: brave
    disabled: false
  - name: bing
    disabled: false
  - name: yandex
    disabled: false
  - name: yahoo
    disabled: false
Y
supervisorctl restart nox_searxng 2>&1 | tail -2
for i in $(seq 1 20); do c=$(curl -s -m3 -o /dev/null -w "%{http_code}" "127.0.0.1:8888/search?q=ping&format=json"); [ "$c" = 200 ] && break; sleep 2; done; echo "up code=$c"
curl -s -m25 "127.0.0.1:8888/search?q=python&format=json" | python3 -c "
import sys,json;d=json.load(sys.stdin);print('results',len(d['results']),sorted({r['engine'] for r in d['results']}),d.get('unresponsive_engines'))" 2>&1 | tail -2
n=$(curl -s -m25 "127.0.0.1:8888/search?q=python&format=json" | python3 -c "import sys,json;print(len(json.load(sys.stdin)['results']))" 2>/dev/null)
if [ "${n:-0}" -lt 1 ]; then cp -a $B $S; supervisorctl restart nox_searxng | tail -1; echo "ROLLED BACK"; else echo "FIX OK n=$n  rollback: cp $B $S"; fi
supervisorctl status nox_searxng | awk '{print $1,$2}'
