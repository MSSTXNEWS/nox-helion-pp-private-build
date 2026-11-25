import sys
p=sys.argv[1] if len(sys.argv)>1 else "/workspace/nox/web/site/nox-chat-rq.js"; s=open(p,encoding="utf-8").read()
if "__rqRender" in s: print("rq2 already"); sys.exit(0)
a="  function render(meta, nox) {"; assert s.count(a)==1
s=s.replace(a,"  window.__rqRender = render;\n"+a,1); open(p,"w",encoding="utf-8").write(s); print("rq2 patched")
