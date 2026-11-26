import json,sys,urllib.request,re,time
D='/workspace/nox/state/mock_qa'
PR=("Ты строгий UX/UI-ревизор. Снимок чата NOX с демо-диалогом (тёмная тема). Оцени 0-10: A (эстетика и аккуратность, ровная сетка кнопок), R (читаемость: шрифт, контраст, колонка чтения), U (удобство: понятность, цели >=44px на мобильном, перекрытия, пустые состояния), WOW (впечатление, сравни с ChatGPT/Claude). "
    "Ответь СТРОГО JSON: {\"A\":число,\"R\":число,\"U\":число,\"WOW\":число,\"issues\":[до 6 коротких проблем],\"fixes\":[до 6 конкретных правок]}")
for w in ("1440","2560","390"):
    body={"image_path":f"{D}/chat_ch_{w}.jpg","prompt":PR,"model":"auto","x_nox_allow_image":True}
    rq=urllib.request.Request("http://127.0.0.1:8793/v1/images/critique",json.dumps(body).encode(),{"Content-Type":"application/json"})
    r=None
    for a in range(4):
        try: r=json.loads(urllib.request.urlopen(rq,timeout=170).read()); break
        except urllib.error.HTTPError as e:
            r={"http":e.code,"body":e.read()[:300].decode('utf8','ignore')}
            if e.code in (400,403): break
            time.sleep(40)
        except Exception as e: r={"err":str(e)[:100]}; time.sleep(30)
    print("== CRIT",w,json.dumps(r,ensure_ascii=False)[:1800],flush=True)
