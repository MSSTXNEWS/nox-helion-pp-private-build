#!/bin/bash
# batch_deploy.sh (серверная часть, запускается через nox-c300.yml: script=batch_deploy.sh). Пакетный деплой файлов на сайт + один QA-прогон.
# Берёт список из nox-control/c300/deploy_manifest.txt (строки "источник_в_c300  путь_на_сайте_относительно_/workspace/nox/web/site", # комментарии).
# Для каждого файла: бэкап в /workspace/nox/web/site_bak/<ts>/ , проверка синтаксиса (.js node --check, .py py_compile, .html/.css только размер>0),
# копирование. Затем ОДИН проход: curl по всем страницам и один Playwright-запуск на все .html (ошибки консоли). При http!=200 у любой страницы: откат из бэкапа.
# Веб-сервер НЕ перезапускается. Ничего не удаляется. Свои логи: /workspace/nox/agent/out/batch_deploy.log
echo "C300: batch_deploy"
S=/workspace/nox/web/site; TS=$(date -u +%Y%m%dT%H%M%S); BK=/workspace/nox/web/site_bak/$TS; LOG=/workspace/nox/agent/out/batch_deploy.log
SRC=/tmp/c300_src_$TS; mkdir -p "$BK" "$SRC"
M=${1:-/tmp/deploy_manifest_$TS.txt}
curl -fsSL --retry 6 --retry-delay 5 --retry-all-errors https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${GITHUB_SHA:-main}/nox-control/c300/deploy_manifest.txt -o "$M" || { echo "нет deploy_manifest.txt"; exit 1; }
PY=/workspace/nox/venv/bin/python; OK=0; BAD=0; PAGES=""
while read -r src dst; do
  case "$src" in ""|\#*) continue;; esac
  f=$SRC/$(basename "$src"); curl -fsSL --retry 6 --retry-delay 5 --retry-all-errors https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${GITHUB_SHA:-main}/nox-control/c300/$src -o "$f" || { echo "FAIL fetch $src"; BAD=$((BAD+1)); continue; }
  [ -s "$f" ] || { echo "FAIL empty $src"; BAD=$((BAD+1)); continue; }
  case "$f" in *.js) node --check "$f" 2>&1 | head -3; [ ${PIPESTATUS[0]} -eq 0 ] || { echo "FAIL js syntax $src"; BAD=$((BAD+1)); continue; };; *.py) $PY -m py_compile "$f" || { echo "FAIL py $src"; BAD=$((BAD+1)); continue; };; esac
  case "$dst" in /*|*..*) echo "FAIL path $dst"; BAD=$((BAD+1)); continue;; esac
  mkdir -p "$BK/$(dirname "$dst")" "$S/$(dirname "$dst")"; [ -e "$S/$dst" ] && cp -p "$S/$dst" "$BK/$dst"
  cp "$f" "$S/$dst" && OK=$((OK+1)) && echo "deployed $dst" && case "$dst" in *.html) PAGES="$PAGES $dst";; esac
done < "$M"
echo "$TS ok=$OK bad=$BAD backup=$BK" | tee -a $LOG
FAILP=0
for p in $PAGES; do c=$(curl -s -o /dev/null -m 10 -w '%{http_code}' http://127.0.0.1:8091/web/$p); echo "http $p $c"; [ "$c" = 200 ] || FAILP=1; done
if [ -n "$PAGES" ] && [ $FAILP -eq 0 ]; then
  export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright
  PAGES="$PAGES" timeout 240 $PY - <<'QA'
import asyncio, os
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch(args=[]); 
    for pg in os.environ["PAGES"].split():
      ctx=await b.new_context(viewport={"width":1280,"height":800}); page=await ctx.new_page(); errs=[]
      page.on("pageerror", lambda e: errs.append(str(e)[:160])); page.on("console", lambda m_: errs.append(m_.text[:160]) if m_.type=="error" else None)
      await page.goto("http://127.0.0.1:8091/web/"+pg, wait_until="load", timeout=30000); await page.wait_for_timeout(1500)
      print("QA", pg, "errors", len(errs), errs[:3]); await ctx.close()
    await b.close()
asyncio.run(m())
QA
fi
if [ $FAILP -ne 0 ]; then echo "ROLLBACK from $BK"; (cd "$BK" && find . -type f | while read -r r; do cp -p "$r" "$S/$r"; done); fi
echo "DONE"
