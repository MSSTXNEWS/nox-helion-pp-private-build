#!/bin/bash
# b_voice_diag.sh: диагностика голоса (обрезка SSML на T7, ударение на «яйца») + скриншоты через найденный интерпретатор с playwright
set -u
W=/workspace/nox
OUT=$W/web/site/qa/voice2
echo "== tts2_server.py defs"
grep -n "def \|sentence\|split" $W/c300_voice/voice2/tts2_server.py | head -80
echo "== ssml func"
awk '/def .*ssml/{f=1} f{print NR": "$0; n++} n>70{exit}' $W/c300_voice/voice2/tts2_server.py
echo "== ru_norm / accent: яйц"
grep -n "яйц\|яиц" $W/c300_voice/voice2/*.py | head -10
echo "== find playwright python"
for py in $(ls -d $W/*/bin/python* $W/tools/*/bin/python* 2>/dev/null) python3 /usr/bin/python3; do
  if $py -c "import playwright" 2>/dev/null; then echo "PY=$py"; break; fi
done
