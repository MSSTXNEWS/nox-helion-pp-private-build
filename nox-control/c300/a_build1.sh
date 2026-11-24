export PATH=/workspace/nox/tools/node/bin:$PATH
S=/workspace/nox/web/site; B=/workspace/nox/build_a; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/a_src
mkdir -p $B/src $S/vendor/nox-chat-ui $S/vendor/nox-brain $S/vendor/nox-fx $S/data
for f in chat-ui.jsx flowpanel.jsx voice.jsx hud.js brain.js nox-fx.js nox-fx.css nui.css nox-brain-x.js nox-brain-x.css nox_a_feed.py; do curl -fsSL "$R/$f?$(date +%s)" -o $B/src/$f || echo FAIL $f; done
cd $B; E="node_modules/.bin/esbuild --bundle --minify --format=esm --log-level=warning --define:process.env.NODE_ENV=\"production\" --loader:.js=jsx --loader:.png=dataurl --loader:.svg=dataurl --loader:.woff2=dataurl --loader:.woff=dataurl"
$E --splitting src/chat-ui.jsx --outdir=$S/vendor/nox-chat-ui 2>&1 | tail -5
$E src/brain.js --outfile=$S/vendor/nox-brain/nox-brain.js 2>&1 | tail -5
$E src/hud.js --outfile=$S/vendor/nox-fx/hud.js 2>&1 | tail -5
ls -la $S/vendor/nox-chat-ui $S/vendor/nox-brain $S/vendor/nox-fx
cd src; for f in nox-fx.js nox-fx.css nox-brain-x.js nox-brain-x.css; do cp -f $f $S/$f; done; cp -f nui.css $S/vendor/nox-chat-ui/nui.css
cp -f nox_a_feed.py /workspace/nox/tools/nox_a_feed.py
pkill -f nox_a_feed.py; nohup setsid python3 /workspace/nox/tools/nox_a_feed.py >/workspace/nox/tools/logs_a_feed.log 2>&1 &
# llm-viz
rm -rf $S/vendor/llm-viz.new 2>/dev/null; cp -r $B/llm-viz/out $S/vendor/llm-viz.new && { [ -d $S/vendor/llm-viz ] && mv $S/vendor/llm-viz $S/vendor/llm-viz.bak_a_1; mv $S/vendor/llm-viz.new $S/vendor/llm-viz; }
python3 - <<'P'
import glob,os,shutil,re
S="/workspace/nox/web/site"
BP=set("cinema music news studio photo voice knowledge memory notes downloads".split())
def bak(p):
    if not os.path.exists(p+".bak_a_1"): shutil.copy2(p,p+".bak_a_1")
n=0
for p in sorted(glob.glob(S+"/*.html")):
    k=os.path.basename(p)[:-5]
    if k in BP: continue
    s=open(p).read()
    if "nox-fx.js" in s or "</head>" not in s: continue
    bak(p); s=s.replace("</head>",'<link rel="stylesheet" href="./nox-fx.css"><script type="module" src="./nox-fx.js"></script>\n</head>',1); open(p,"w").write(s); n+=1
print("fx tagged",n)
def edit(f,old,new):
    p=S+"/"+f; s=open(p).read()
    if new in s: return
    bak(p); assert old in s,(f,old); open(p,"w").write(s.replace(old,new,1))
edit("chat.html","</body>",'<link rel="stylesheet" href="./vendor/nox-chat-ui/chat-ui.css"><link rel="stylesheet" href="./vendor/nox-chat-ui/nui.css">\n<script type="module" src="./vendor/nox-chat-ui/chat-ui.js"></script>\n</body>')
for f in ("consciousness","organism","soul","growth","selffeel","training"):
    edit(f+".html","</body>",'<link rel="stylesheet" href="./nox-brain-x.css">\n<script type="module" src="./nox-brain-x.js"></script>\n</body>')
P
sleep 20
for u in chat.html vendor/nox-chat-ui/chat-ui.js vendor/nox-brain/nox-brain.js vendor/llm-viz/llm.html vendor/llm-viz/_next/static data/organs_hist.jsonl data/train_logs.json nox-fx.js; do echo "$u $(curl -s -o /dev/null -w '%{http_code}' 127.0.0.1:8091/web/$u)"; done
