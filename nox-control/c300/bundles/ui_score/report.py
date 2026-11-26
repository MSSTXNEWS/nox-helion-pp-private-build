#!/usr/bin/env python3
"""Сводка U и A по формуле из UX_SCORES.md. Читает /workspace/nox/agent/out/ui_sc/*.json"""
import json,glob,sys,os
OUT='/workspace/nox/agent/out/ui_sc'
def load(p):
    try: return json.load(open(p))
    except Exception: return None
def lh_scores(d):
    if not d: return None
    c=d.get('categories',{}); g=lambda k:(c.get(k,{}).get('score') or 0)*100
    return {'a11y':g('accessibility'),'bp':g('best-practices'),'perf':g('performance')}
W={'critical':2,'serious':2,'moderate':1,'minor':0.5,None:1}
pages=sorted({os.path.basename(f).split('_')[0] for f in glob.glob(OUT+'/*_own.json')})
rows=[]
for pg in pages:
    Us=[];As=[];det={}
    for vp in('1440','390'):
        o=load(f'{OUT}/{pg}_{vp}_own.json'); l=lh_scores(load(f'{OUT}/{pg}_{vp}_lh.json'))
        if not o or 'error' in o: continue
        V=sum(W.get(a.get('imp'),1)*min(a['n'],5) for a in o.get('axe',[]))
        T=o['small']; H=1 if o['hs'] else 0; C=1 if o['cta'] else 0; E=min(1,o['jserr']+ (1 if o['err404']>2 else 0)); M=1 if o['theme'] else 0
        u_own=10-min(4,0.25*V)-min(2,0.2*T)-1.5*H-1.0*(1-C)-3*E
        u=0.6*max(0,u_own)+0.4*((l['a11y']/10) if l else max(0,u_own))
        a_own=10-5*(1-M)-min(3,0.3*T)-2*H-1.5*E
        a=(0.3*max(0,a_own)+0.4*(l['bp']/10)+0.3*(l['perf']/10)) if l else max(0,a_own)
        Us.append(max(0,min(10,u)));As.append(max(0,min(10,a)))
        det[vp]=f"V{V:.1f} T{T} H{H} C{C} E{E} M{M}"+(f" lh{l['a11y']:.0f}/{l['bp']:.0f}/{l['perf']:.0f}" if l else ' lh-')
    if Us: rows.append((pg,sum(Us)/len(Us),sum(As)/len(As),det))
print('page | U | A | detail(1440 ; 390)   V=axe-weighted T=<44px H=hscroll C=cta E=errors M=theme lh=a11y/bp/perf')
for pg,u,a,det in rows: print(f"{pg:12s} U={u:.1f} A={a:.1f} | {det.get('1440','-')} ; {det.get('390','-')}"+("  <8" if min(u,a)<8 else ""))
print('MEAN U=%.2f A=%.2f n=%d'%(sum(r[1] for r in rows)/max(1,len(rows)),sum(r[2] for r in rows)/max(1,len(rows)),len(rows)))
