#!/bin/bash
# Отмена старых pending + постановка новых задач NOX (план v4). Бэкап очереди рядом, откат: cp queue.jsonl.bak_c93 queue.jsonl
cd /root/nox/state/dispatcher || exit 1
B=queue.jsonl.bak_c93; [ -f $B ] || cp -p queue.jsonl $B
python3 - <<'P'
import json,time,os
TS=time.strftime('%Y-%m-%d %H:%M:%S')+' Europe/Moscow (UTC+3)'
rows=[json.loads(l) for l in open('queue.jsonl') if l.strip()]
n=0
for t in rows:
    if t.get('status')=='pending':
        t['status']='cancelled'; t['note']=('отменено владельцем 21.11 (замена на задачи плана v4); бэкап queue.jsonl.bak_c93')[:300]; t['finished_at']=TS; n+=1
tmp='queue.jsonl.tmp'
open(tmp,'w').write('\n'.join(json.dumps(t,ensure_ascii=False) for t in rows)+'\n'); os.replace(tmp,'queue.jsonl')
print('cancelled pending:',n)
NEW=[
('N01','Освоить 31 инструмент самоулучшения: прогнать registry/tests в /root/nox/selftools, записать в память, что работает','nox-control/selftools/registry.py; отчёт в /root/nox/state/NOX_N01.md'),
('N02','Прочитать «Исполнительный пакет v4» (Google Диск) и записать роли: S1 Мозг (Квебек, GLM-5.3, судьи, чат), S2 Учебка (всё обучение), запреты плана','конспект ролей и запретов в памяти NOX'),
('N03','Замер базовой скорости S2 (ток/с, TTFT p50/p95) после возобновления — один рычаг за раз, журнал A/B','таблица замеров в журнале'),
('N04','Собрать обучающий корпус (corpus_build): цель ≥2000 строк, чистка, разбиение train/val','файл корпуса + статистика'),
('N05','Бэкап адаптеров, памяти и скриптов: на Google Диск (<100 МБ/файл) и на ПК через warm_weights.backup_push когда канал поднят','список бэкапов + контрольные суммы'),
('N06','Чат /health: разобрать причину сбоя selfheal «chat /health failed», предложить плейбук (рестарт чата — зона владельца)','диагноз + плейбук в отчёте'),
('N07','Подготовить перенос памяти S03/Engram и судей на S1 (список файлов, размеры, порядок), без запуска','план миграции'),
('N08','Подготовить экзамен NOX для сравнения GLM-5.3 и DeepSeek: код, веб, рассуждения, русский, личность, память','набор тестов + критерий: не хуже и ≥3 ток/с'),
]
with open('owner_inbox.jsonl','a') as f:
    for i,t,a in NEW:
        f.write(json.dumps({"id":"v4."+i,"class":"owner_order","priority":0,"deps":[],"handler":"track","title":"[v4] "+i+": "+t,"status":"pending","lane":"owner_order","source":"owner_v4_21_11","acceptance":a,"ts":TS},ensure_ascii=False)+'\n')
print('new tasks:',len(NEW))
P
tail -n 1 owner_inbox.jsonl | cut -c1-200
