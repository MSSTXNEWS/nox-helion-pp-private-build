echo "K1: ln_t4"
export RUNNER_TRACKING_ID=""
S=/workspace/nox/tools/searxng_conf/settings.yml
wc -l $S; grep -vE "secret_key|^\s*#" $S | head -80 | cut -c1-120
cd /workspace/nox/tools/searxng 2>/dev/null; for e in brave bing mojeek wikipedia startpage qwant yandex "yep" "marginalia" "bing news" "wikidata" "stract" "presearch" "yahoo"; do curl -s -m15 "127.0.0.1:8888/search?q=python+language&format=json&engines=$(echo $e | sed 's/ /+/g')" | python3 -c "
import sys,json;d=json.load(sys.stdin);print('$e',len(d['results']),[u[1] for u in d.get('unresponsive_engines',[])][:1])" 2>&1 | tail -1; done
