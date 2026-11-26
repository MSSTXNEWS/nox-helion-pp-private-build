echo "C300: ui_wd6 (FASTWOW: пакет + его index)"
S=/workspace/nox/web/site; F=/workspace/nox/web/v29src/FASTWOW/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
BK=/workspace/nox/web/ix_bak_$TS; mkdir -p $BK; cp -p index.html $BK/index.html
n0=$(find $S -type f | wc -l)
# все файлы пакета, которых нет на сайте (корень без html, кроме index; и каталоги), существующие не трогаем
for f in $(cd $F && ls | grep -vE '\.html$'); do [ -f $F/$f ] && { [ -e $S/$f ] || cp -p $F/$f $S/$f; }; done
for d in $(cd $F && ls -d */ | tr -d / | grep -vE '^(pc|qa|tools|legacy|reference)$'); do mkdir -p $S/$d; cp -an $F/$d/. $S/$d/ 2>/dev/null; done
echo "files added: $(( $(find $S -type f | wc -l) - n0 ))"
python3 - <<'P'
S='/workspace/nox/web/site'; F='/workspace/nox/web/v29src/FASTWOW/site'
s=open(F+'/index.html',encoding='utf-8').read()
hook='<script>if(/[?&]legacy=1/.test(location.search))location.replace("index-legacy.html"+location.search)</script>'
s=s.replace('<head>','<head>'+hook,1) if '<head>' in s else hook+s
open(S+'/index.html','w',encoding='utf-8').write(s)
P
echo "== five-worlds in index: $(grep -c five-worlds index.html)"; ls assets13 2>/dev/null | head -3; ls vendor/assets13 2>/dev/null | head -3
curl -fsSL --retry 5 https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ui_worlds/shots.py -o /tmp/shots.py
$PY -c "import PIL;print('PIL',PIL.__version__)" 2>&1 | tail -1
timeout 200 $PY /tmp/shots.py index 1440 900 ix1440 helion,chronos,somnium,forge,synapse
echo "ROLLBACK_HINT cp -p $BK/index.html $S/index.html"
