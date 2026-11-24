import sys; sys.argv=["x"]
exec(open("/workspace/nox/c300_dl_libs.py").read().split("take(\"monaco\"")[0])
import shutil
for n in ("reveal","maplibre"): shutil.rmtree(os.path.join(V,n), ignore_errors=True)
take("reveal", "reveal.js", ["dist/reveal.js", "dist/reveal.css", "dist/theme/black.css", "plugin/markdown/markdown.js"], ver="5.1.0")
take("maplibre", "maplibre-gl", ["dist/maplibre-gl.js", "dist/maplibre-gl.css"], ver="4.7.1")
import re
src=open("/workspace/nox/web/site/nox-tools.js").read()+open("/workspace/nox/web/site/tv.html").read()
miss=[f for f in sorted(set(re.findall(r"X \+ '([^']+\.(?:js|css|mjs))'", src)+re.findall(r'vendor/nox-x/([^"\']+\.(?:js|css))', src))) if not os.path.exists(os.path.join(V,f))]
print("missing referenced:", miss)
