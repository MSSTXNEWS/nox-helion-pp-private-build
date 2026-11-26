import sys,json
from playwright.sync_api import sync_playwright
A=open('/workspace/nox/tools/uiscore/node_modules/axe-core/axe.min.js').read()
with sync_playwright() as p:
    b=p.chromium.launch()
    for q in ('?a11y=0','','?x=1'):
        pg=b.new_page(viewport={'width':1440,'height':900})
        pg.goto('http://127.0.0.1:8091/web/calendar.html'+q,wait_until='load');pg.wait_for_timeout(4000)
        pg.add_script_tag(content=A)
        r=pg.evaluate("axe.run(document,{resultTypes:['violations']}).then(r=>r.violations.map(v=>[v.id,v.impact,v.nodes.length,v.nodes[0].failureSummary.slice(0,400),v.nodes[0].html.slice(0,120)]))")
        print('Q',q or 'none',json.dumps(r,ensure_ascii=False)[:1800],flush=True)
        if q=='':
            print('GRID',pg.evaluate("(function(){var t=document.querySelector('.fc-scrollgrid');return t?t.outerHTML.slice(0,900):'no'})()"))
        pg.close()
    b.close()
