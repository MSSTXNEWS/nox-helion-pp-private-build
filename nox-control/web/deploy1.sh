#!/bin/bash
W=/root/nox/web; A=https://api.github.com/repos/MSSTXNEWS/nox-helion-pp-private-build/contents/nox-control/web/files
for f in nox-web-extras.js nox-web-extras.css templates.html; do curl -fsSL -H "Accept: application/vnd.github.raw" "$A/$f?ref=main" -o $W/$f.new && mv $W/$f.new $W/$f && echo "put $f $(wc -c <$W/$f)"; done
mkdir -p /root/nox/web_bak_extras
for h in $W/*.html; do b=$(basename $h); grep -q nox-web-extras $h && continue; [ -f /root/nox/web_bak_extras/$b ] || cp $h /root/nox/web_bak_extras/$b
 python3 -I - "$h" <<'P'
import sys
p=sys.argv[1]; s=open(p,encoding='utf-8').read()
tag='<link rel="stylesheet" href="./nox-web-extras.css"><script defer src="./nox-web-extras.js"></script>'
i=s.lower().rfind('</body>')
s=s[:i]+tag+s[i:] if i>=0 else s+tag
open(p,'w',encoding='utf-8').write(s)
P
 echo "inj $b"; done | tr '\n' ' '; echo
for p in settings memory chat templates index; do echo "$p $(curl -s -o /dev/null -w %{http_code} http://127.0.0.1:8091/web/$p.html)"; done
curl -s http://127.0.0.1:8091/web/nox-web-extras.js | head -c 60; echo
