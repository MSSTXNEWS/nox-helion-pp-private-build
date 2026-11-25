#!/usr/bin/env python3
"""TH: строит nox-graphite-map.css из всех CSS и <style> сайта: каждое правило с тёплым (красно-оранжевым) цветом
дублируется под html[data-nox-theme=graphite] с цветом, переведённым в серо-голубую гамму. Без зависимостей.
Использование: th_gen_map.py SITE_DIR OUT_FILE"""
import re,sys,os,glob,colorsys
SITE=sys.argv[1]; OUT=sys.argv[2]
_gc=open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'nox-graphite.css'),encoding='utf-8').read()
OWN=set(re.findall(r'(--[\w-]+)\s*:',_gc.split('/* Фон')[0]))
P='html[data-nox-theme=graphite]'
ACC=(157,177,209)
DANGER=re.compile(r'stop|danger|error|\berr\b|\.err|\.bad|-bad|fail|alert|delete|\.del\b|remove|crit|\.no\b|\bred\b|-red|\.off\b|reject|deny|invalid',re.I)
COL=re.compile(r'rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(?:,\s*([\d.]+%?)\s*)?\)|#([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b')
def clamp(v): return max(0,min(255,int(round(v))))
def conv(m,danger):
  if m.group(1) is not None:
    r,g,b=int(m.group(1)),int(m.group(2)),int(m.group(3)); a=m.group(4); hexform=False
  else:
    h=m.group(5)
    if len(h)==3: h=''.join(c*2 for c in h)
    r,g,b=int(h[0:2],16),int(h[2:4],16),int(h[4:6],16); a=None; hexform=True
    if len(h)==8: a=str(round(int(h[6:8],16)/255,3))
  mx,mn=max(r,g,b),min(r,g,b)
  if mx<6 or r<g or r<b: return m.group(0)
  chroma=(mx-mn)/255.0
  if (r-b)/max(mx,1)<.12 or (r-b)<4 and mx>40: return m.group(0)
  hh,ll,ss=colorsys.rgb_to_hls(r/255,g/255,b/255); hd=hh*360
  if not(hd<=62 or hd>=340): return m.group(0)
  if danger and (hd<=12 or hd>=340): return m.group(0)
  L=(r*.2126+g*.7152+b*.0722)/255
  if chroma>.5 and L>.5:
    k=min(1.15,L/.66); n=(clamp(ACC[0]*k),clamp(ACC[1]*k),clamp(ACC[2]*k))
  else:
    Y=L*255; n=(clamp(Y-2),clamp(Y),clamp(Y+5))
  if hexform and a is None: return '#%02x%02x%02x'%n
  if a is None: return 'rgb(%d,%d,%d)'%n
  return 'rgba(%d,%d,%d,%s)'%(n+(a,))
def conv_value(v,danger):
  parts=re.split(r'(url\([^)]*\))',v); ch=False; out=[]
  for p in parts:
    if p.startswith('url('): out.append(p); continue
    q=COL.sub(lambda m:conv(m,danger),p)
    if q!=p: ch=True
    out.append(q)
  return ''.join(out),ch
def split_top(s,sep):
  res=[];d=0;cur='';q=None
  for c in s:
    if q:
      cur+=c
      if c==q: q=None
      continue
    if c in '"\'': q=c;cur+=c;continue
    if c in '([': d+=1
    elif c in ')]': d-=1
    if c==sep and d==0: res.append(cur);cur=''
    else: cur+=c
  if cur.strip(): res.append(cur)
  return res
def pre(sel):
  sel=sel.strip()
  if not sel or sel.startswith('@') : return None
  if sel.startswith(':root'): return P+sel[5:]
  if re.match(r'html(?![\w-])',sel): return P+sel[4:]
  return P+' '+sel
def process(css,top=True):
  css=re.sub(r'/\*.*?\*/','',css,flags=re.S); out=[]; i=0; n=len(css)
  while i<n:
    j=css.find('{',i)
    if j<0: break
    head=css[i:j].strip(); d=1;k=j+1;q=None
    while k<n and d:
      c=css[k]
      if q:
        if c==q: q=None
      elif c in '"\'': q=c
      elif c=='{': d+=1
      elif c=='}': d-=1
      k+=1
    body=css[j+1:k-1]; i=k
    if head.startswith('@media') or head.startswith('@supports') or head.startswith('@layer'):
      inner=process(body,False)
      if inner: out.append(head+'{'+inner+'}')
    elif head.startswith('@'): continue
    else:
      danger=bool(DANGER.search(head)); decls=[]
      for dcl in split_top(body,';'):
        if ':' not in dcl: continue
        pn,pv=dcl.split(':',1); pn=pn.strip(); pv=pv.strip()
        if not pv or pn in OWN: continue
        nv,ch=conv_value(pv.replace('!important','').strip(),danger)
        if ch: decls.append(pn+':'+nv+'!important')
      if decls:
        sels=[pre(s) for s in split_top(head,',')]; sels=[s for s in sels if s]
        if sels: out.append(','.join(sels)+'{'+';'.join(decls)+'}')
  return ''.join(out)
src=[]
skip=('nox-graphite','th_')
for f in sorted(glob.glob(os.path.join(SITE,'*.css'))):
  b=os.path.basename(f)
  if b.startswith(skip) or '.bak' in b: continue
  src.append((b,open(f,encoding='utf-8',errors='ignore').read()))
for f in sorted(glob.glob(os.path.join(SITE,'*.html'))):
  t=open(f,encoding='utf-8',errors='ignore').read()
  for m in re.finditer(r'<style[^>]*>(.*?)</style>',t,flags=re.S): src.append((os.path.basename(f),m.group(1)))
# JSSTR: CSS внутри строк JS (инжектируемые стили)
STR=re.compile(r"'((?:[^'\\\n]|\\.){20,}?)'|`((?:[^`\\]|\\.){20,}?)`")
VALID=re.compile(r'^[^{}]+\{[^{}]*\}$')
for f in sorted(glob.glob(os.path.join(SITE,'*.js'))):
  b=os.path.basename(f)
  if '.bak' in b or b.startswith(('nox-icons','nox-theme')): continue
  try: t=open(f,encoding='utf-8',errors='ignore').read()
  except Exception: continue
  if 'rgba(' not in t and '#' not in t: continue
  for m in STR.finditer(t):
    sv=(m.group(1) or m.group(2) or '')
    if '{' not in sv or ':' not in sv or sv.count('{')!=sv.count('}'): continue
    if not COL.search(sv) : continue
    sv=sv.replace('\\n',' ').replace("\\'","'")
    if re.search(r'function|=>|return |\bconst\b|\blet\b|\$\{',sv): continue
    src.append((b,sv))
seen=set(); res=['/* NOX TH: авто-карта «Графит» (th_gen_map.py). Тёплые цвета исходных стилей переведены в серо-голубую гамму. Не править руками. */']
for b,c in src:
  r=process(c)
  if b.endswith('.js'): r=''.join(x for x in re.findall(r'(?:@media[^{]*\{(?:[^{}]*\{[^{}]*\})+\}|[^{}]+\{[^{}]*\})',r) if (x.startswith('@media') or VALID.match(x)) and not re.search(r'graphite\] [a-z][a-z0-9]*(?:[,{ ]|$)',x))
  if r and r not in seen: seen.add(r); res.append(r)
open(OUT,'w',encoding='utf-8').write('\n'.join(res))
print('map bytes',os.path.getsize(OUT),'sources',len(src))
