cat > /tmp/s5_vp.py <<'P'
import re,shutil,time,py_compile
f="/workspace/nox/qa_audit.py"; s=open(f).read()
if "S5VENDOR2" in s: print("OUT: already"); raise SystemExit
a=s.index('res["vendor_used"] = await pg.evaluate("""'); b=s.index('""", VENDOR_OK)',a)+len('""", VENDOR_OK)')
shutil.copy(f,f+".bak_s5_"+time.strftime("%H%M"))
js = r"""res["vendor_used"] = await pg.evaluate(r\"\"\"async(names)=>{const urls=[...document.scripts].map(s=>s.src).concat([...document.querySelectorAll('link[rel=stylesheet]')].map(l=>l.href)).filter(u=>u.startsWith(location.origin));let t=document.documentElement.outerHTML;for(const u of urls){try{t+=await (await fetch(u)).text()}catch(e){}}const out=new Set();let m;const r1=/vendor\/(nox-x|nox-lib)\/([\w.-]+)/g;while((m=r1.exec(t)))out.add(m[2].replace(/\.(js|css|mjs)$/,''));const r2=/vendor\/(nox-extra|fx)\/([\w.-]+?)\.(js|css|mjs)/g;while((m=r2.exec(t)))out.add(m[2]);const r3=/vendor\/([\w.-]+)\//g;while((m=r3.exec(t))){if(!['nox-x','nox-lib','nox-extra','fx'].includes(m[1]))out.add(m[1])}return [...out]}\"\"\", VENDOR_OK)  # S5VENDOR2"""
js = js.replace('\\"','"')
s = s[:a]+js+s[b:]
open(f,"w").write(s); py_compile.compile(f,doraise=True); print("OUT: patched v2")
P
/workspace/nox/venv/bin/python /tmp/s5_vp.py 2>&1 | tail -3
cat > /tmp/s5_chain3.sh <<'C'
for p in atlas settings; do
  flock /tmp/qaa.lock nice -n 5 /workspace/nox/venv/bin/python /workspace/nox/qa_audit.py $p.html >> /tmp/s5_chain3.log 2>&1
done
echo CHAIN_DONE >> /tmp/s5_chain3.log
C
if /workspace/nox/venv/bin/python -m py_compile /workspace/nox/qa_audit.py; then : > /tmp/s5_chain3.log; setsid nohup bash /tmp/s5_chain3.sh >/dev/null 2>&1 < /dev/null & echo "OUT: chain3 started"; fi
