echo "C300: w_q1"
N=/workspace/nox; export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
cat > /tmp/q1.py <<'P'
import sys
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--use-angle=swiftshader','--enable-unsafe-swiftshader','--no-sandbox'])
    for pagename in ('chat-dc','chat'):
        pg=b.new_page(viewport={'width':1440,'height':900});rs=[]
        pg.on('response',lambda r:rs.append((int(r.headers.get('content-length') or 0),r.url.split('/web/')[-1][:80])))
        pg.goto('http://127.0.0.1:18091/web/%s.html'%pagename,wait_until='load');pg.wait_for_timeout(9000)
        js=sum(s for s,u in rs if '.js' in u.split('?')[0]);print('==',pagename,'n',len(rs),'totalKB',sum(s for s,u in rs)//1024,'jsKB',js//1024)
        rs.sort(reverse=True)
        for s,u in rs[:16]:print(s//1024,u)
        import collections
        c=collections.Counter(u.split('/')[1] if u.startswith('vendor/') else 'own' for s,u in rs);print(dict(c))
        pg.close()
    b.close()
P
timeout 120 $N/venv/bin/python /tmp/q1.py 2>&1 | cut -c1-160
