#!/bin/bash
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright
PY=/workspace/nox/venv/bin/python
cat > /tmp/am.py <<'P'
import asyncio,base64,io,json
from playwright.async_api import async_playwright
from PIL import Image
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={"width":1440,"height":900}); errs=[]
        pg.on("pageerror",lambda e:errs.append(str(e)[:150]))
        bad='{"nodes":[{"id":1,"text":"Маркетинг","group":"Рост"},{"id":2,"text":"Реклама","group":"Рост"},{"id":3,"text":"MVP","group":"Продукт"},{"id":4,"text":"Тесты","group":"Продукт"},{"id":5,"text":"Бюджет","group":"Финансы"},{"id":6,"text":"Договоры","group":"Финансы"}],"links":[[1,2],[3,4],[5,6]'
        body=json.dumps({"message":{"role":"assistant","content":bad},"done":False},ensure_ascii=False)+"\n"
        await pg.route("**/api/chat",lambda r:r.fulfill(status=200,content_type="application/x-ndjson",body=body))
        await pg.goto("http://127.0.0.1:8091/web/board.html"); await pg.wait_for_timeout(5000)
        await pg.fill("#bdIn","запуск"); await pg.click('[data-a="ai"]'); await pg.wait_for_timeout(9000)
        print("status",await pg.inner_text("#bdSt"),"elements",await pg.evaluate("()=>NOXBoard&&NOXBoard.api?NOXBoard.api().getSceneElements().length:'n/a'"))
        raw=await pg.screenshot(type="jpeg",quality=60); im=Image.open(io.BytesIO(raw)).convert('RGB'); im=im.resize((900,562)); bb=io.BytesIO(); im.save(bb,'JPEG',quality=34); s=base64.b64encode(bb.getvalue()).decode()
        print("B64_ai_mock_BEGIN"); [print(s[i:i+900]) for i in range(0,len(s),900)]; print("B64_ai_mock_END"); print("errs",errs)
        await b.close()
asyncio.run(main())
P
$PY /tmp/am.py 2>&1 | tail -c 120000
