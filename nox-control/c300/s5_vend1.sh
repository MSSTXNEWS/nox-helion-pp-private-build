cat > /tmp/vnames.json <<'J'
["3d-force-graph", "ag-ui", "assistant-ui", "blocknote", "boardgame-io", "broadcast-channel", "butterchurn", "canvas-confetti", "chessground", "chrono-node", "circuitsvis", "cmdk", "cobe", "codemirror", "colorjs.io", "cosmos-gl", "d3", "d3-celestial", "d3-sankey", "d3-shape", "dagre", "dashjs", "deep-chat", "dnd-kit-core", "drawio", "earth", "echarts", "embla-carousel", "excalidraw-excalidraw", "fabric", "fast-average-color", "ffmpeg", "ffmpeg-core", "ffmpeg-util", "file-type", "foliate-js", "fontsource-doto", "frappe-gantt", "fuse.js", "globe-gl", "grapesjs", "graphology", "gsap", "highlight.js", "hls.js", "howler", "html-to-image", "img-comparison-slider", "ios-haptics", "jsonforms", "jupyterlite", "katex", "kbar", "konva", "lightweight-charts", "lindenmayer", "liquid-glass-react", "lrc-kit", "maplibre-gl", "markdown-it", "masonry", "mermaid", "meyda", "nipplejs", "nosleep.js", "novnc", "ogl", "orama-orama", "page-flip", "paper-design-shaders", "pdf-lib", "pdfjs", "peerjs", "perspective-transform", "phaser", "pixi-filters", "pixi.js", "pmtiles", "qrcode", "react-markdown", "readability", "resonance-audio", "reveal.js", "ricky0123-vad-web", "rive", "rjsf-core", "schedule-x-calendar", "shaka-player", "sigma", "simplex-noise", "sonner", "sortablejs", "style-dictionary", "suncalc", "tesseract", "theatre", "three-vrm", "tinykeys", "tone", "transformers-js", "tremor", "ts-fsrs", "tsparticles", "tweakpane", "typewriter-effect", "uplot", "uppy-core", "vidstack", "vidstack-react", "vis-timeline", "webmidi", "xterm", "xyflow", "y-webrtc", "yjs", "zustand"]
J
cat > /tmp/s5_pvend.py <<'PYEOF'
import sys,shutil,time,py_compile,json
f="/workspace/nox/qa_audit.py"; s=open(f).read()
if "S5VENDOR" in s: print("OUT: already"); sys.exit()
shutil.copy(f,f+".bak_s5_"+time.strftime("%H%M"))
NAMES=json.loads(open("/tmp/vnames.json").read())
s=s.replace("HANDMADE = {","# S5VENDOR\nVENDOR_OK = %r\nHANDMADE = {" % NAMES,1)
old='            await pg.keyboard.press("Escape")\n'
new='''            if vp == "desk":
                try:
                    res["vendor_used"] = await pg.evaluate("""async(names)=>{const urls=[...document.scripts].map(s=>s.src).concat([...document.querySelectorAll('link[rel=stylesheet]')].map(l=>l.href)).filter(u=>u.startsWith(location.origin));let t=document.documentElement.outerHTML;for(const u of urls){try{t+=await (await fetch(u)).text()}catch(e){}}return names.filter(n=>t.includes('vendor/'+n+'/'))}""", VENDOR_OK)
                except Exception as e:
                    res["vendor_used"] = []
'''+old
assert old in s; s=s.replace(old,new,1)
old2="    hm = bool(j.get(\"handmade\")) or bool(j.get(\"toporno\"))\n"
assert old2 in s
s=s.replace(old2,old2+"    lowv = len(res.get(\"vendor_used\", [])) < 2\n    hm = hm or lowv\n",1)
open(f,"w").write(s); py_compile.compile(f,doraise=True); print("OUT: patched vendor")
PYEOF
/workspace/nox/venv/bin/python /tmp/s5_pvend.py
grep -c S5VENDOR /workspace/nox/qa_audit.py
