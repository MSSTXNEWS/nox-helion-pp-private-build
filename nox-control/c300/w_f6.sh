echo "C300: w_f6"
S=/workspace/nox/web/site; N=/workspace/nox; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
python3 - <<'P'
import glob,os
S='/workspace/nox/web/site/';m=[]
for f in sorted(glob.glob(S+'*.html')):
    b=os.path.basename(f)
    if b in('index.html','chat-dc.html') or 'legacy' in b or b.endswith('.main.html') or b.startswith('qa-') or 'bak' in b: continue
    s=open(f,encoding='utf-8',errors='replace').read();ch=0
    if 'nox-a11y-fix' not in s:
        if '</body>' in s: i=s.rindex('</body>')
        elif '</html>' in s: i=s.rindex('</html>')
        else: i=len(s)
        s=s[:i]+'<script src="./nox-a11y-fix.js?v=1" defer></script>\n'+s[i:];ch=1;m.append(b+':a11y')
    if 'nox-theme.js' not in s and '<meta charset' in s:
        j=s.index('>',s.index('<meta charset'))+1;s=s[:j]+'\n<script src="./nox-theme.js"></script>'+s[j:];ch=1;m.append(b+':theme')
    if ch: open(f,'w',encoding='utf-8').write(s)
print('patched',m)
P
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
curl -fsSL "$R/w_a11y/axe_scan.py?cb=$(date +%s)" -o /tmp/axe_scan.py
timeout 100 $N/venv/bin/python /tmp/axe_scan.py live 2>&1 | cut -c1-400
