#!/bin/bash
S=/workspace/nox/web/site
cd $S; ls | head -80; echo ---; wc -c web/chat.html web/index.html web/cinema.html web/music.html 2>&1
ls web | head -100
echo ---REWORK; ls qa/rework; for f in chat index cinema music; do echo "== $f"; cat qa/rework/$f.json 2>/dev/null | head -c 2500; done
echo ---NAV; python3 -c "
import json;d=json.load(open('$S/nav.json') if __import__('os').path.exists('$S/nav.json') else open('$S/web/nav.json'));print(json.dumps(d,ensure_ascii=False)[:2500])"
echo ---JS; ls web/js web/assets web/vendor 2>/dev/null | head -60
