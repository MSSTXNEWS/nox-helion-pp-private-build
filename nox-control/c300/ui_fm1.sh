echo "C300: ui_fm1"
S=/workspace/nox/web/site
/workspace/nox/venv/bin/python - <<'P'
import json,re,glob,os
S='/workspace/nox/web/site'
nav={}
try:
    j=json.load(open(S+'/nav.json'))
    def walk(o,g=''):
        if isinstance(o,dict):
            u=o.get('href') or o.get('url') or o.get('path')
            if isinstance(u,str): nav[os.path.basename(u.split('?')[0]).replace('.html','')]=(g,o.get('title') or o.get('name') or o.get('label') or '')
            for k,v in o.items():
                if isinstance(v,(list,dict)): walk(v,o.get('title') or o.get('name') or o.get('id') or g if isinstance(o.get('title') or o.get('name') or o.get('id'),str) else g)
        elif isinstance(o,list):
            for v in o: walk(v,g)
    walk(j)
except Exception as e: print('NAVERR',e)
ENG=['fullcalendar','echarts','uPlot','cytoscape','excalidraw','leaflet','vidstack','filerobot','swiper','three','gridstack','d3','codemirror','wavesurfer','hls','howler','tsparticles','gsap','lottie','shoelace','katex','konva','fabric','vis-timeline','frappe','dexie','deep-chat','globe']
rows=[]
for f in sorted(glob.glob(S+'/*.html')):
    n=os.path.basename(f)[:-5]; s=open(f,errors='ignore').read()
    srcs=re.findall(r'src="([^"]+)"',s)
    inl=sum(len(m) for m in re.findall(r'<script(?![^>]*src)[^>]*>(.*?)</script>',s,re.S))
    sh=[os.path.basename(x).split('?')[0][:-3] for x in srcs if re.search(r'nox-(p|s2|s4|s6|k\d)-?',x) and 'nox-k4-core' not in x and 'k8-meta' not in x]
    en=sorted({e for e in ENG if any(e.lower() in x.lower() for x in srcs)})
    g=nav.get(n,('-',''))
    rows.append((n,len(s),inl,'UX' if 'nox-u-ux' in s else '-',g[0][:14],g[1][:22],','.join(en),len([x for x in sh]),','.join(sh[:3])))
print('PAGES',len(rows),'NAVENTRIES',len(nav),'notinsite',[k for k in nav if not os.path.exists(S+'/'+k+'.html')][:40])
for r in rows: print('|'.join(map(str,r)))
P
