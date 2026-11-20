#!/usr/bin/env python3
"""c52: подключает модули пунктов 26–52 в веб-сборку NOX. Идемпотентно. usage: apply_c52.py BUILD_DIR [MODULES_DIR]"""
import glob, os, shutil, sys
B = sys.argv[1]; M = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(os.path.abspath(__file__))
ALL = ["nox-v14-ai2", "nox-v14-res", "nox-v14-fx"]
CHAT = ["nox-v14-ai3", "nox-v14-ai4", "nox-v14-ai5", "nox-v14-ai6"]
for n in ALL + CHAT:
    for ext in (".js", ".css"):
        src = os.path.join(M, n + ext)
        if os.path.exists(src) and os.path.abspath(src) != os.path.abspath(os.path.join(B, n + ext)): shutil.copy2(src, os.path.join(B, n + ext))
done = 0
for f in glob.glob(os.path.join(B, "*.html")):
    s = open(f, encoding="utf-8").read()
    if "nox-v14-shell.js" not in s: continue
    mods = ALL + (CHAT if os.path.basename(f) == "chat.html" else [])
    css = "".join('<link rel="stylesheet" href="./%s.css">' % n for n in mods if ("%s.css" % n) not in s and os.path.exists(os.path.join(B, n + ".css")))
    js = "".join('<script defer src="./%s.js"></script>' % n for n in mods if ("%s.js" % n) not in s)
    if css: s = s.replace("</head>", css + "</head>", 1)
    if js: s = s.replace("</body>", js + "</body>", 1)
    if css or js: open(f, "w", encoding="utf-8").write(s); done += 1
print("c52 applied to", done, "pages")
