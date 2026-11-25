python3 - <<'P'
import json,os,time
R="/workspace/nox/web/site/qa/rework/"
V={
"music":"ВОЗВРАТ (05:55): шапка по-прежнему сдвинута и обрезана («ТЧЕР»), авто-аудит 7 [6,8,7]; чип МУЗЫКА / МУЗЫКА дублируется.",
"studio":"ВОЗВРАТ (05:55): masonry с реальными фото — шаг вперёд, но у большинства карточек под фото огромные пустые тёмные блоки и горизонтальные полосы-артефакты; авто-аудит 7 [6,8,5], статус owner.",
"news":"НА ПРОВЕРКЕ (05:55): шапка исправлена, нижний ряд с картинками, вид Google News; ждёт авто-аудит A/R/U>=8 (последний 04:07 устарел).",
"settings":"НА ПРОВЕРКЕ (05:55): все 10 планет с реальными текстурами, миры интерфейса с превью, 404 нет; визуально соответствует macOS Settings; ждёт авто-аудит A/R/U>=8."}
for k,t in V.items():
    f=R+k+".json"
    j=json.load(open(f)) if os.path.exists(f) else {"page":k+".html","cycle":0,"fails":[]}
    j["s5_verdict"]={"ts":time.strftime("%F %T"),"text":t}
    json.dump(j,open(f,"w"),ensure_ascii=False,indent=1)
print("OUT: ok")
P
