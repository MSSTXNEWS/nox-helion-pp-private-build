S=/workspace/nox/web/site
cd $S
[ -f x.txt ] && cp -p x.txt x.txt.bak_s1_$(date +%H%M%S)
base64 -d > x.txt <<'S1EOF'
eAo=
S1EOF
echo OK x.txt $(wc -c <x.txt)
cd /workspace/nox/web/site
grep -n "textarea\|input\|getSelection\|context\|ctx\|nmc-panel\|className" nox-minichat.js | cut -c1-220 | head -24
curl -s -m10 "http://127.0.0.1:8091/svc/advisors/suggest?project=&dialog=test&last=hello" | head -c 500; echo
curl -s -m10 "http://127.0.0.1:8091/svc/advisors/draft?page=chat&text=Составь%20план" | head -c 400; echo
curl -s -m10 http://127.0.0.1:8091/svc/advisors/pins | head -c 300; echo
curl -s -m10 "http://127.0.0.1:8091/svc/nox-living/meta?cid=s1-meta" | head -c 300
