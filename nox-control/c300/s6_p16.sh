echo S4RUN:s6_p16
cd /workspace/nox/web/site/qa/rework
printf '%s\n' 'S6 real page: Leaflet карта (OSM, выбор города sl-select, геолокация) + вкладка Глобус (vendor/earth); вместо заглушки; в nav.json группа ВИДЖЕТЫ, бэкап nav.json.bak_s6_1, qa_ctl --pin выполнен.' > map.fixed
printf '%s\n' 'S6 real page: foliate-js читалка (EPUB/FB2/MOBI/AZW3/CBZ, оглавление в sl-drawer, прогресс sl-progress-bar); в nav КОНСТРУКТОР.' > book-reader.fixed
printf '%s\n' 'S6 real page: уведомления - разрешение браузера, сбои служб из /api/nox-live, тест через NOXcmd notify.test, журнал; в nav СИСТЕМА. Outbox (pc_outbox) через API недоступен - не используется.' > notifications.fixed
printf '%s\n' 'S6 real page: бенчмарк из qa/audit.json - ECharts (тема nox) A/R/U по страницам, порог 8, карточки принято/ниже порога; в nav СИСТЕМА.' > benchmark.fixed
printf '%s\n' 'S6 real page: граф страниц NOX на cytoscape из nav.json, переход на страницу; в nav КОНСТРУКТОР.' > nexus.fixed
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
cat > /tmp/s6_p16.py <<'PYEOF'
import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--use-gl=swiftshader"])
        pg=await (await b.new_context(viewport={"width":1440,"height":900})).new_page()
        await pg.goto("http://127.0.0.1:8091/web/settings.html",wait_until="domcontentloaded",timeout=60000); await pg.wait_for_timeout(5000)
        for name in ["Циан","Янтарь","Мята","Фиолет","Малина","Лазурь"]:
            loc=pg.locator('.nxwd button[aria-label="%s"]'%name); await loc.scroll_into_view_if_needed(timeout=3000); await loc.click(timeout=3000,force=True); await pg.wait_for_timeout(600)
            r=await pg.evaluate("()=>[getComputedStyle(document.documentElement).getPropertyValue('--nox-world-rgb').trim(),localStorage.getItem('nox.world.pal')]")
            print("PAL",name,r,"OK" if r[0]==r[1] else "MISMATCH")
asyncio.run(main())
PYEOF
$PY /tmp/s6_p16.py 2>&1 | tail -8
