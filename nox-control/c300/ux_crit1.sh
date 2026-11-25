echo "C300: ux_crit1"
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/0aa6a17991d053b4852f89a4354e1e541c8a4c36/nox-control/c300/bundles/ux_crit/mock_system.jpg -o /tmp/mock_system.jpg || { echo FAIL; exit 0; }
python3 - <<'PY'
import json,base64,urllib.request
b=base64.b64encode(open('/tmp/mock_system.jpg','rb').read()).decode()
body={"image_b64":b,"prompt":"Оцени удобство интерфейса (юзабилити) страницы: 0-10, перечисли проблемы и исправления. Данные макета пустые.","model":"auto"}
rq=urllib.request.Request("http://127.0.0.1:8793/v1/images/critique",json.dumps(body).encode(),{"Content-Type":"application/json"})
try: r=urllib.request.urlopen(rq,timeout=120); print("HTTP",r.status,r.read()[:900])
except urllib.error.HTTPError as e: print("HTTP",e.code,e.read()[:500])
except Exception as e: print("ERR",e)
PY
