S=/workspace/nox/web/site
cd $S && python3 -I - <<'PY'
import json,re,os,glob
nav=json.load(open('nav.json'))
pages=[]
for g in nav['groups']:
    for it in g['items']:
        pages.append(it['file'])
pages=sorted(set(pages))
def rd(p):
    try: return open(p,encoding='utf-8',errors='ignore').read()
    except: return ''
def sz(p):
    try: return os.path.getsize(p)
    except: return 0
def vsize(v):
    t=0
    for r,d,f in os.walk(v):
        for x in f:
            if x.endswith(('.js','.css','.mjs')): t+=sz(os.path.join(r,x))
    return t
srcs={}
for p in pages:
    h=rd(p); srcs[p]=h
cnt={}
for p,h in srcs.items():
    for m in set(re.findall(r'(?:src|href)=["\']\.?/?(?:web/)?([^"\'?#]+\.(?:js|css))',h)):
        cnt[m]=cnt.get(m,0)+1
common={k for k,v in cnt.items() if v>=len(pages)*0.5}
out=[]
for p in pages:
    h=srcs[p]
    files=set(re.findall(r'(?:src|href)=["\']\.?/?(?:web/)?([^"\'?#]+\.(?:js|css))',h))
    own=[f for f in files if re.match(r'(.*/)?nox-[^/]*\.(js|css)$',f) and f not in common and not f.startswith('vendor/')]
    ownl=[f for f in files if not f.startswith('vendor/') and f not in common and f not in own and os.path.exists(f)]
    inl_js=sum(len(x) for x in re.findall(r'<script(?![^>]*src)[^>]*>(.*?)</script>',h,re.S))
    inl_css=sum(len(x) for x in re.findall(r'<style[^>]*>(.*?)</style>',h,re.S))
    ojs=sum(sz(f) for f in own if f.endswith('.js')); ocss=sum(sz(f) for f in own if f.endswith('.css'))
    ojs+=sum(sz(f) for f in ownl if f.endswith('.js')); ocss+=sum(sz(f) for f in ownl if f.endswith('.css'))
    owntext=h+''.join(rd(f) for f in own+ownl)
    vend=set(re.findall(r'vendor/([A-Za-z0-9_.@-]+)/',owntext))
    vend|=set(re.findall(r'vendor/([A-Za-z0-9_.@-]+)/',''.join(rd(f) for f in files if f in common and 'dock' in f)) ) if False else set()
    vsz=sum(vsize('vendor/'+v) for v in vend if os.path.isdir('vendor/'+v))
    body=re.sub(r'<script.*?</script>|<style.*?</style>','',h,flags=re.S)
    own_ctl=len(re.findall(r'<(button|input|select|textarea)\b',owntext))
    sl=len(re.findall(r'<sl-[a-z-]+',owntext))
    tl=len(re.findall(r'<(button|input|select|textarea)\b',body))
    out.append(dict(page=p,own_js=ojs+inl_js,own_css=ocss+inl_css,own_files=own+ownl,html=len(h),vendor_used=sorted(vend),vendor_bytes=vsz,ctl_own=own_ctl,ctl_html=tl,sl=sl))
print('COMMON',sorted(common))
print('JSON',json.dumps(out,ensure_ascii=False))
PY
echo QA_FILES; ls qa | grep -v -E 'audit_|\.jpg|\.png' | head -60
for p in index chat cinema music news settings photo atlas about system; do echo "QAP $p"; for f in qa/$p.json qa/rework/$p.json; do [ -f $f ] && head -c 1800 $f; done; echo; done
