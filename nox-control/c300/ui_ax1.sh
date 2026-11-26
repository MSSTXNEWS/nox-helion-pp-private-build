echo "C300: ui_ax1"
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright
/workspace/nox/venv/bin/python - <<'P'
from playwright.sync_api import sync_playwright
AX='/workspace/nox/tools/uiscore/node_modules/axe-core/axe.min.js'
with sync_playwright() as p:
    b=p.chromium.launch()
    for pg in ['settings','calendar','photo']:
        x=b.new_page(viewport={'width':1440,'height':900}); x.goto(f'http://127.0.0.1:8091/web/{pg}.html',wait_until='domcontentloaded'); x.wait_for_timeout(5000)
        x.add_script_tag(path=AX)
        r=x.evaluate("async()=>(await axe.run(document,{resultTypes:['violations']})).violations.map(v=>[v.id,v.impact,v.nodes.length,v.nodes.slice(0,3).map(n=>n.target.join(' ')+' :: '+n.html.slice(0,110))])")
        print('==',pg)
        for v in r: print(v[0],v[1],v[2]); [print('   ',n) for n in v[3]]
        x.close()
    b.close()
P
