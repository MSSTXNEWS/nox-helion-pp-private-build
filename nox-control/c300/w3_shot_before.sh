R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
curl -fsSL $R/shot.py -o /tmp/w3shot.py
/workspace/nox/venv/bin/python /tmp/w3shot.py chatB http://127.0.0.1:8091/web/chat.html indexB http://127.0.0.1:8091/web/index.html cinemaB http://127.0.0.1:8091/web/cinema.html musicB http://127.0.0.1:8091/web/music.html 2>&1 | tail -400
S=/workspace/nox/web/site; cd $S
echo ==JS; sed -n '56,70p;105,135p;150,170p' nox-wow.js | cut -c1-900
