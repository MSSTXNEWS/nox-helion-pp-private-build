S=/workspace/nox/web/site
cd $S
echo IDX; ls -la --time-style=+%F_%T index*.html | grep -v bak_ | cut -c1-200; ls index*.html | grep bak | head -20 | tr '\n' ' '
echo; echo EXTRA_PAGES
python3 -I - <<'PY'
import json,re,os
nav=json.load(open('nav.json'))
n=sum(len(g['items']) for g in nav['groups']); soon=[i['file'] for g in nav['groups'] for i in g['items'] if i.get('soon')]
print('nav items',n,'soon',soon)
allp=sorted(f for f in os.listdir('.') if f.endswith('.html'))
navf={i['file'] for g in nav['groups'] for i in g['items']}
print('html not in nav:',[f for f in allp if f not in navf and '.bak' not in f])
common=set('manifest.js nox-4k.css nox-actions.js nox-cast-btn.js nox-cmd.js nox-dock-pop.js nox-ds.css nox-ds.js nox-fx.css nox-fx.js nox-gesture.js nox-live.js nox-m-mobile.css nox-m-mobile.js nox-menu-x.css nox-minichat.js nox-nav-x.js nox-nav.js nox-ninja.js nox-pages.css nox-pult.js nox-pwa.js nox-radial.js nox-s6-sl.js nox-s6.css nox-state.js nox-sun-x.js nox-theme.js nox-unify.css nox-vt.css nox-worlds.css nox-worlds.js nox-wow.css'.split())
def rd(p):
    try:return open(p,encoding='utf-8',errors='ignore').read()
    except:return ''
def sz(p):
    try:return os.path.getsize(p)
    except:return 0
def vsize(v):
    t=0
    for r,d,f in os.walk(v):
        for x in f:
            if x.endswith(('.js','.css','.mjs')):t+=sz(os.path.join(r,x))
    return t
for p in ['index.html','atlas.html','finance.html','assistant.html','mode.html','creative.html','editor.html','games.html','mail.html','map.html','nexus.html','social.html','money.html','calls.html','contacts.html','events.html','messenger.html','notifications.html','benchmark.html','browser.html','book-reader.html','ai-learning.html','advisors.html']:
    h=rd(p)
    if not h: print('MISSING',p); continue
    files=set(re.findall(r'(?:src|href)=["\']\.?/?(?:web/)?([^"\'?#]+\.(?:js|css))',h))
    own=[f for f in files if not f.startswith('vendor/') and f not in common and os.path.exists(f)]
    ojs=sum(sz(f) for f in own if f.endswith('.js'))+sum(len(x) for x in re.findall(r'<script(?![^>]*src)[^>]*>(.*?)</script>',h,re.S))
    ocss=sum(sz(f) for f in own if f.endswith('.css'))+sum(len(x) for x in re.findall(r'<style[^>]*>(.*?)</style>',h,re.S))
    t=h+''.join(rd(f) for f in own)
    vend=sorted(set(re.findall(r'vendor/([A-Za-z0-9_.@-]+)/',t)))
    vs=sum(vsize('vendor/'+v) for v in vend if os.path.isdir('vendor/'+v))
    ctl=len(re.findall(r'<(?:button|input|select|textarea)\b',t)); sl=len(re.findall(r'<sl-[a-z-]+',t))
    print('PG',json.dumps(dict(page=p,own_js=ojs,own_css=ocss,files=own,vendor=vend,vbytes=vs,ctl=ctl,sl=sl),ensure_ascii=False))
PY
echo SELECTS; for f in $(ls *.html | grep -v bak); do n=$(grep -o '<select' $f | wc -l); [ $n -gt 0 ] && echo "$f $n"; done | tr '\n' ';'
echo; echo ANM $(grep -l 'ANM-0' *.js 2>/dev/null | head -5 | tr '\n' ' ') cnt $(cat nox-*.js | grep -o 'ANM-[0-9]*' | sort -u | wc -l)
echo WORLDS $(grep -o -i -E 'CHRONOS|SOMNIUM|FORGE|SYNAPSE|HELION' nox-worlds.js | sort | uniq -c | tr '\n' ' ')
echo COLORS $(grep -o -E 'glacier|ion|amethyst|platinum|copper|gold' nox-worlds.js | sort | uniq -c | tr '\n' ' ')
echo VOICE $(grep -o -i -E 'male|мужск|auto.?voice|pickVoice|chooseVoice' nox-voice-*.js nox-persona.js 2>/dev/null | sort | uniq -c | head -8 | tr '\n' ' ')
echo NOXSELF $(grep -l -E 'self.?(theme|ui|music)|nox.?(set|change)Theme|autoTheme' nox-*.js 2>/dev/null | head -5 | tr '\n' ' ')
echo MUSICAUTO $(grep -l -i -E 'bgm|ambient|fonovaya|фонов.{0,8}музык' nox-*.js 2>/dev/null | head -5 | tr '\n' ' ')
echo QUICKTAGS $(grep -l -E 'quick|nox-qtag|cmd-tag|qtag|тег' nox-chat-*.js | head -5 | tr '\n' ' ')
echo HUD $(grep -c 'nox-hud' index.html chat.html system.html 2>/dev/null | tr '\n' ' ')
echo STUBS $(grep -l -i -E 'заглушк|coming soon|скоро будет|lorem ipsum|TODO' $(ls *.html | grep -v bak) 2>/dev/null | tr '\n' ' ')
echo R2; head -c 5000 qa/r2_verdicts.md
echo AUDITKEYS; python3 -I -c "
import json
a=json.load(open('qa/audit.json'))
print(type(a), list(a)[:5] if isinstance(a,dict) else len(a))
for p in ['index','chat','cinema','music','news','settings','photo','atlas','about','system']:
    d=a.get(p) or a.get(p+'.html') or (a.get('pages',{}) or {}).get(p) if isinstance(a,dict) else None
    print('A',p,json.dumps(d,ensure_ascii=False)[:1300] if d else None)
"
