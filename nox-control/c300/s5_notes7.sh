python3 - <<'P'
import json,os,time
R="/workspace/nox/web/site/qa/rework/"
N={
"settings":["Ручной просмотр S5, 03:46. macOS Settings: сайдбар и стеклянные плашки хорошие, это правильное направление. Но блок «Планета фона»: 4 из 10 плиток (Юпитер, Сатурн, Уран, Нептун) пустые тёмные квадраты без текстуры, и при загрузке 404 на vendor/planets/2k/nox-mercury.jpg, nox-venus.jpg, nox-earth.jpg (пункт 9). Скачать/положить реальные текстуры (например NASA/Solar System Scope, CC) и превью для всех планет, не оставлять пустых плиток.","Плитки «Мир интерфейса» (CHRONOS, SOMNIUM, FORGE, SYNAPSE) без превью-картинок — выглядят заглушками; добавить миниатюры реальных миров."],
"nav":["Ручной просмотр S5, 03:46. nav.html не существует (404): автоаудит проверять нечего. Приёмка меню/дока делается вручную на всех страницах: верхняя шапка и две строки нижней панели видны, но в 2 ряда внизу плотно и мелко; нужны стеклянные выпадающие меню и мобильная шторка — проверю кликами, когда S3 даст сценарий проверки."]}
for k,v in N.items():
    f=R+k+".json"
    j=json.load(open(f)) if os.path.exists(f) else {"page":k+".html","cycle":0,"fails":[]}
    j["s5_review"]={"ts":time.strftime("%F %T"),"notes":v}
    j["fails"]=[x for x in j.get("fails",[]) if not str(x.get("item","")).startswith("РУЧНОЙ")]+[{"item":"РУЧНОЙ ПРОСМОТР S5 (приоритетнее авто-замечаний)","detail":v}]
    json.dump(j,open(f,"w"),ensure_ascii=False,indent=1)
print("ok")
P
