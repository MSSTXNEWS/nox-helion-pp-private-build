echo "C300: k4_probe_1"
S=/workspace/nox/web/site; cd $S
ls vendor | tr '\n' ' '; echo
for p in atlas calendar index news design photo system; do echo "=== $p"; wc -c $p.html; grep -oE "<script[^>]*src=[^>]*>" $p.html | sed 's/<script //' | tr '\n' ' ' | cut -c1-900; echo; grep -oE 'id="[^"]+"' $p.html | tr '\n' ' ' | cut -c1-1500; echo; done
echo "=== qa"; ls -la /tmp/k2_qa.py; cat /tmp/k2_qa.py | head -40
