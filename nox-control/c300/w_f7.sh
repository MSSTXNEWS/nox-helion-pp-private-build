echo "C300: w_f7"
S=/workspace/nox/web/site; N=/workspace/nox; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
python3 - <<'P'
p='/workspace/nox/web/site/studio.html';s=open(p,encoding='utf-8').read()
t='\n<script src="./nox-theme.js"></script>'
if s.count('nox-theme.js')==1 and t in s: open(p,'w',encoding='utf-8').write(s.replace(t,'',1));print('studio theme removed')
else: print('studio unchanged',s.count('nox-theme.js'))
P
bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
cmp $S/studio.html $N/web/pkg/webroot/studio.html && echo synced
