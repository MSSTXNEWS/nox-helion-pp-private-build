import sys,json
from playwright.sync_api import sync_playwright
A=open('/workspace/nox/tools/uiscore/node_modules/axe-core/axe.min.js').read()
with sync_playwright() as p:
    b=p.chromium.launch()
    for n in sys.argv[1:]:
      for w in (390,1440):
        pg=b.new_page(viewport={'width':w,'height':900})
        try:
            pg.goto('http://127.0.0.1:8091/web/%s.html'%n,wait_until='load',timeout=30000);pg.wait_for_timeout(3000)
            pg.add_script_tag(content=A)
            r=pg.evaluate("axe.run(document,{resultTypes:['violations']}).then(r=>r.violations.map(v=>[v.id,v.impact,v.nodes.length,v.nodes[0].target.join(' ').slice(0,70),(v.nodes[0].html||'').slice(0,90)]))")
            print(n,w,json.dumps(r,ensure_ascii=False),flush=True)
        except Exception as e: print(n,w,'ERR',str(e)[:80])
        pg.close()
    b.close()
