import sys
p="/workspace/nox/web/site/nox-chat-rq.js"; s=open(p,encoding="utf-8").read()
if "rq-pending" in s: print("rq already"); sys.exit(0)
R=[("if (o.meta) meta = o.meta; if (o.nox) nox = o.nox;","if (o.meta) meta = o.meta; if (o.nox) nox = o.nox; if (o.t === 'meta2' && o.meta) { const mm = o.meta; setTimeout(() => render(mm, nox), 0); }"),
("old && old.remove();","old && old.remove(); a.querySelectorAll('.rq-think').forEach((x) => x.remove());"),
("meta.emo || meta.judges != null || meta.thought","meta.emo || meta.pending || meta.judges != null || meta.thought"),
("    if (meta && meta.judges != null) { const jd","    if (meta && meta.pending) { const pj = document.createElement('div'); pj.className = 'rq-judge rq-pending'; pj.setAttribute('role', 'status'); pj.textContent = 'проверяется…'; d.prepend(pj); }\n    if (meta && meta.judges != null) { const jd")]
for x,y in R:
    assert s.count(x)==1,(x,s.count(x)); s=s.replace(x,y,1)
open(p,"w",encoding="utf-8").write(s); print("rq patched")
