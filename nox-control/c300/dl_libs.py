"""c300: скачать 20 модулей с npm (tarball) в site/vendor/nox-x/<имя>/. Только нужные dist-файлы. Отчёт в stdout."""
import json, os, tarfile, io, urllib.request, shutil, sys
V = "/workspace/nox/web/site/vendor/nox-x"; os.makedirs(V, exist_ok=True)
def tgz(pkg, ver="latest"):
    meta = json.load(urllib.request.urlopen("https://registry.npmjs.org/%s/%s" % (pkg.replace("/", "%2f"), ver), timeout=60))
    data = urllib.request.urlopen(meta["dist"]["tarball"], timeout=300).read()
    return meta["version"], tarfile.open(fileobj=io.BytesIO(data), mode="r:gz")
def take(name, pkg, files, ver="latest", tree=None):
    out = os.path.join(V, name); os.makedirs(out, exist_ok=True)
    try:
        v, t = tgz(pkg, ver); n = 0
        for m in t.getmembers():
            p = m.name.split("/", 1)[1] if "/" in m.name else m.name
            ok = p in files or (tree and any(p.startswith(x) for x in tree))
            if ok and m.isfile():
                dst = os.path.join(out, p if tree and any(p.startswith(x) for x in tree) else os.path.basename(p))
                os.makedirs(os.path.dirname(dst), exist_ok=True); open(dst, "wb").write(t.extractfile(m).read()); n += 1
        open(os.path.join(out, "VERSION"), "a").write("%s@%s\n" % (pkg, v)); print("OK", name, pkg, v, n, "files")
    except Exception as e: print("FAIL", name, pkg, e)
take("monaco", "monaco-editor", [], tree=["min/vs/"])
take("xterm", "@xterm/xterm", ["lib/xterm.js", "css/xterm.css"])
take("xterm", "@xterm/addon-fit", ["lib/addon-fit.js"])
take("react", "react", ["umd/react.production.min.js"], ver="18.3.1")
take("react", "react-dom", ["umd/react-dom.production.min.js"], ver="18.3.1")
take("excalidraw", "@excalidraw/excalidraw", [], ver="0.17.6", tree=["dist/"])
take("quill", "quill", ["dist/quill.js", "dist/quill.snow.css", "dist/quill.bubble.css"])
take("tabulator", "tabulator-tables", ["dist/js/tabulator.min.js", "dist/css/tabulator_midnight.min.css"])
take("xlsx", "xlsx", ["dist/xlsx.full.min.js"])
take("mammoth", "mammoth", ["mammoth.browser.min.js"])
take("pdflib", "pdf-lib", ["dist/pdf-lib.min.js"])
take("tesseract", "tesseract.js", ["dist/tesseract.min.js", "dist/worker.min.js"], ver="5.1.1")
take("tesseract", "tesseract.js-core", ["tesseract-core-simd-lstm.wasm.js", "tesseract-core-simd-lstm.wasm", "tesseract-core-lstm.wasm.js", "tesseract-core-lstm.wasm"], ver="5.1.1")
take("uppy", "uppy", ["dist/uppy.min.js", "dist/uppy.min.css"], ver="3.27.3")
take("cropper", "cropperjs", ["dist/cropper.min.js", "dist/cropper.min.css"], ver="1.6.2")
take("gantt", "frappe-gantt", ["dist/frappe-gantt.min.js", "dist/frappe-gantt.min.css", "dist/frappe-gantt.css"], ver="0.6.1")
take("markmap", "d3", ["dist/d3.min.js"], ver="7.9.0")
take("markmap", "markmap-lib", ["dist/browser/index.iife.js"], ver="0.17.2")
take("markmap", "markmap-view", ["dist/browser/index.js"], ver="0.17.2")
take("reveal", "reveal.js", ["dist/reveal.js", "dist/reveal.css", "dist/theme/black.css", "plugin/markdown/markdown.js"])
take("maplibre", "maplibre-gl", ["dist/maplibre-gl.js", "dist/maplibre-gl.css"])
take("globe", "globe.gl", ["dist/globe.gl.min.js"])
take("tone", "tone", ["build/Tone.js"])
take("butterchurn", "butterchurn", ["lib/butterchurn.min.js"], ver="2.6.7")
take("butterchurn", "butterchurn-presets", ["lib/butterchurnPresets.min.js"], ver="2.4.7")
take("vad", "@ricky0123/vad-web", ["dist/bundle.min.js", "dist/vad.worklet.bundle.min.js", "dist/silero_vad_legacy.onnx", "dist/silero_vad_v5.onnx"], ver="0.0.22")
take("vad", "onnxruntime-web", ["dist/ort.min.js", "dist/ort-wasm-simd-threaded.wasm", "dist/ort-wasm-simd-threaded.mjs"], ver="1.20.1")
# Yjs: ESM-бандл с зависимостями (lib0) через esm.sh
try:
    os.makedirs(os.path.join(V, "yjs"), exist_ok=True)
    stub = urllib.request.urlopen("https://esm.sh/yjs@13.6.20?bundle&target=es2022", timeout=120).read().decode()
    import re as _re
    path = _re.findall(r'["\'](/[^"\']+\.mjs)["\']', stub)[-1]
    code = urllib.request.urlopen("https://esm.sh" + path, timeout=120).read()
    open(os.path.join(V, "yjs", "yjs.bundle.mjs"), "wb").write(code); print("OK yjs", path, len(code))
except Exception as e: print("FAIL yjs", e)
# языки OCR
for lang in ("rus", "eng"):
    try:
        d = urllib.request.urlopen("https://tessdata.projectnaptha.com/4.0.0_fast/%s.traineddata.gz" % lang, timeout=300).read()
        open(os.path.join(V, "tesseract", lang + ".traineddata.gz"), "wb").write(d); print("OK tessdata", lang, len(d))
    except Exception as e: print("FAIL tessdata", lang, e)
os.system("du -sh %s; du -sh %s/* | sort -h | tail -6" % (V, V))
