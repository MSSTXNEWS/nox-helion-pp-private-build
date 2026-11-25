echo S4RUN:s4_rc13
S=/workspace/nox/web/site; cd $S
for p in mail messenger social calls contacts finance games book-reader pdf marketing map spaces notifications forge nexus weights benchmark models connections; do echo "== $p $(wc -c < $p.html) $(grep -o 'nox-p-[a-z-]*\.js' $p.html | head -1) $(grep -o 'data-page="[a-z]*"' $p.html)"; sed -n '/<main/,/<\/main>/p' $p.html | sed 's/<[^>]*>/ /g' | tr -s ' \n' ' ' | cut -c1-230; echo; done
cat svc/../qa/registry.json >/dev/null 2>&1
python3 -c "
import json;print(list(json.load(open('/workspace/nox/web/pkg/server/svc_registry.json')).keys())[:30])" 2>&1 | head -3
for n in actual stirling radicale; do echo $n $(curl -s -m5 -o /dev/null -w '%{http_code}' 127.0.0.1:8091/svc/$n/) $(curl -s -m5 127.0.0.1:8091/svc/$n/ | grep -c 'src="/'); done
