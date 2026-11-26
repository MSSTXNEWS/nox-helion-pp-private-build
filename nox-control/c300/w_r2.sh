echo "C300: w_r2"
python3 - <<'P'
import glob,re
for f in glob.glob('/workspace/nox/web/site/*.js')+glob.glob('/workspace/nox/web/site/studio.html'):
    s=open(f,errors='ignore').read()
    for k in ('nox-ui-button','nox-wow-button-skin','noxUiButton','buttonSkin'):
        for m in list(re.finditer(k,s))[:2]:
            print(f.split('/')[-1],k,'|',s[max(0,m.start()-120):m.end()+180].replace('\n',' ')[:320])
P
