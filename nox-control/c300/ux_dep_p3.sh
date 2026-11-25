echo "C300: ux_dep_p3"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; export PATH=/workspace/nox/tools/node/bin:$PATH
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/828dc0cc903c07fe45756706a545d7a1bb7a388e/nox-control/c300/bundles/ux_p3
curl -fsSL --retry 5 --retry-delay 4 --retry-all-errors $RAW/patch.py -o /tmp/ux_p3_patch.py && curl -fsSL --retry 5 $RAW/qa_fast.py -o /tmp/ux_qa_fast.py || { echo FAIL_FETCH; exit 0; }
python3 /tmp/ux_p3_patch.py ux$TS
python3 /tmp/ux_qa_fast.py && python3 -m py_compile /workspace/nox/qa_audit.py && echo QAFAST_OK || { cp $(ls -t /workspace/nox/qa_audit.py.bak_ux_fast_* | head -1) /workspace/nox/qa_audit.py; echo QAFAST_ROLLBACK; }
grep -c QA_FAST /workspace/nox/qa_audit.py
echo == textures
mkdir -p assets/nox-approved/hdr assets/nox-approved/metal vendor/nox-planets
[ -s assets/nox-approved/hdr/machine_shop_01_1k.hdr ] || curl -fsSL -m 90 --retry 3 https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/1k/machine_shop_01_1k.hdr -o assets/nox-approved/hdr/machine_shop_01_1k.hdr || rm -f assets/nox-approved/hdr/machine_shop_01_1k.hdr
if [ ! -s assets/nox-approved/metal/Metal012_1K-JPG_Color.jpg ]; then curl -fsSL -m 90 --retry 3 "https://ambientcg.com/get?file=Metal012_1K-JPG.zip" -o /tmp/m012.zip && (cd /tmp && python3 -c "import zipfile;z=zipfile.ZipFile('m012.zip');z.extract('Metal012_1K-JPG_Color.jpg','/tmp/m012')" ) && cp /tmp/m012/Metal012_1K-JPG_Color.jpg assets/nox-approved/metal/ || echo METAL_FAIL; fi
[ -s vendor/nox-planets/2k_moon.jpg ] || curl -fsSL -m 60 https://www.solarsystemscope.com/textures/download/2k_moon.jpg -o vendor/nox-planets/2k_moon.jpg || { rm -f vendor/nox-planets/2k_moon.jpg; echo MOON_FAIL; }
[ -s vendor/nox-planets/nox-mars.jpg ] || curl -fsSL -m 60 https://www.solarsystemscope.com/textures/download/2k_mars.jpg -o vendor/nox-planets/nox-mars.jpg || { rm -f vendor/nox-planets/nox-mars.jpg; echo MARS_FAIL; }
file assets/nox-approved/hdr/* assets/nox-approved/metal/* vendor/nox-planets/*.jpg 2>&1 | cut -c1-140
echo == QA
cat > /tmp/ux_p3_qa.py <<'PYX'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch()
    for pg in ['qa','board','about','integrations']:
        for w in (1440,390):
            c=b.new_context(viewport={'width':w,'height':850});g=c.new_page();er=[];ex=[]
            g.on('pageerror',lambda e:er.append(str(e)[:100]))
            g.on('request',lambda r:ex.append(r.url[:60]) if 'unpkg' in r.url else None)
            try:
                g.goto('http://127.0.0.1:8091/'+pg+'.html',wait_until='load',timeout=25000);g.wait_for_timeout(3000)
                hs=g.evaluate('document.documentElement.scrollWidth-innerWidth')
            except Exception as e: hs='ERR'
            print('QA',pg,w,'hscroll',hs,'EXC' if er else 'ok',er[:2],'unpkg',ex[:2]);c.close()
    b.close()
PYX
timeout 120 /workspace/nox/venv/bin/python /tmp/ux_p3_qa.py | tee /tmp/ux_p3_qa.out
grep -E "^QA.*EXC" /tmp/ux_p3_qa.out && { for f in qa.html board.html; do b=$(ls -t $f.bak_ux_ux$TS 2>/dev/null|head -1); [ -n "$b" ] && cp $b $f; done; echo ROLLBACK_ALL; } || echo QA_CLEAN
echo == очередь быстрого аудита
O=/workspace/nox/agent/out; pkill -f ux_aud_p1.sh; pkill -f ux_aud_p2.sh
cat > $O/ux_fast1.sh <<'AEOF'
O=/workspace/nox/agent/out
while pgrep -f u_audit5.sh >/dev/null; do sleep 30; done
for p in system widgets memory map cinema knowledge projects pdf atlas board qa about integrations; do
  QA_FAST=1 flock /tmp/qaa.lock /workspace/nox/venv/bin/python /workspace/nox/qa_audit.py $p.html > $O/ux_f_$p.out 2>&1
  python3 - $p <<'PY' >> $O/ux_f_prog.txt
import json,sys
d=json.load(open('/workspace/nox/web/site/qa/audit.json',encoding='utf-8')).get(sys.argv[1],{})
print(sys.argv[1],d.get('ts'),'wow',d.get('wow'),'ARU',d.get('ARU'),'fix',[str(x)[:70] for x in d.get('fix',[])][:3],'fails',[f.get('item','')[:25] for f in d.get('fails',[])][:3])
PY
done; echo FIN >> $O/ux_f_prog.txt
AEOF
rm -f $O/ux_f_prog.txt; setsid nohup bash $O/ux_fast1.sh >/dev/null 2>&1 </dev/null &
sleep 1; pgrep -fa "ux_fast1|ux_aud" | cut -c1-90
