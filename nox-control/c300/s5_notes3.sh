python3 - <<'P'
import json,os,time
R="/workspace/nox/web/site/qa/rework/"
N={"training":["Ручной просмотр S5, 03:00. W&B: первый экран занимает таблица органов (моно-шрифт, простая таблица), графики потерь ушли ниже сгиба и сжаты до одной полосы. Как у W&B: слева список запусков (run cards) с цветом линии, справа сетка графиков ECharts (loss, lr, VRAM) крупно, сверху панель метрик-плиток (шаг, loss, VRAM, ETA).","Таблицу «Органы и процессы» перенести в свёрнутую панель «Система» (Grafana-стиль статус-плитки: зелёный/красный индикатор вместо слов «жив»/«нет ответа»).","Две ошибки 400 на /memory/api при загрузке страницы (пункт 9 чек-листа): убрать запрос или исправить параметры.","Кнопки применить/скачать/дистиллировать на карточках не видны на первом экране; команды training.apply/download/distill теперь в реестре (confirm:true, ответ 501 «бэкенд не подключён» — показывать пользователю честно «недоступно»)."]}
for k,v in N.items():
    f=R+k+".json"
    j=json.load(open(f)) if os.path.exists(f) else {"page":k+".html","cycle":0,"fails":[]}
    j["s5_review"]={"ts":time.strftime("%F %T"),"notes":v}
    j["fails"]=[x for x in j.get("fails",[]) if not str(x.get("item","")).startswith("РУЧНОЙ")]+[{"item":"РУЧНОЙ ПРОСМОТР S5 (приоритетнее авто-замечаний)","detail":v}]
    json.dump(j,open(f,"w"),ensure_ascii=False,indent=1)
print("ok")
P
