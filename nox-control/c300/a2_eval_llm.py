#!/usr/bin/env python3
"""Честный eval паспорта намерения: LLM-советник через шлюз :8793 (без регулярок и без подсказок). Эталоны размечены по смыслу реальных формулировок владельца/координатора."""
import json, re, sys, time, urllib.request
CASES = [  # (фраза, глагол, останавливать_текущее: True/False/None=не проверять)
 ('возьми забытое, быстрое добавь сейчас, остальное раздели на V2 и V3, текущее не останавливай', 'add', False),
 ('Добавь к пункту 2 задачу остановленного агента V', 'add', False),
 ('Добавь к работе идеи из сна, ничего не останавливай', 'add', False),
 ('когда просит «добавь» — добавлять, а не останавливать, переносить или сужать то, что уже в работе', 'add', False),
 ('Замени самых дешёвых субагентов, которые не справлялись, на хороших недорогих', 'replace', None),
 ('Нельзя, чтобы кейсы были подогнаны под регулярки, прогоняй через LLM-советника', 'other', False),
 ('Если это зависшие тесты или дубли, закрой их', 'stop', None),
 ('Диспетчер перегружен, разберись чьи это задачи', 'other', False),
 ('Один шаг на один запуск больше не делай, собирай 5–10 действий в один скрипт', 'other', False),
 ('Ускорь сервер NOX и обучение, остальное не трогай', 'speed', False),
 ('Останови агента A, его заменяет A2', 'stop', True),
 ('Перенеси задачи про охоту червей в V2', 'move', True),
 ('Раздели остальное на очереди V2 и V3, текущее продолжай', 'split', False),
 ('Скачай готовое решение для очереди задач из интернета', 'download', False),
 ('Доведи 3 живые задачи из чата до артефакта', 'finish', False),
 ('Удали старые дубли задач из очереди', 'delete', None),
 ('Подключи в шлюз 2-3 бесплатных советника по рисованию', 'add', False),
 ('Замени судью на другую модель', 'replace', True),
 ('Останови обучение на час', 'stop', True),
 ('Добавь кнопку «подумай глубже», остальное оставь как есть', 'add', False),
]
HOLD = [('Добавь в студию кнопку скачать, остальное не трогай', 'add', False), ('Останови сервер обучения до утра', 'stop', True), ('Доделай карточку червей и покажи в чате', 'finish', False),
 ('Перенеси охоту червей на ночь', 'move', True), ('Замени модель судьи на более лёгкую', 'replace', True), ('Ускорь ответы чата, обучение не останавливай', 'speed', False),
 ('Скачай из интернета готовую библиотеку для очередей', 'download', False), ('Раздели задачи на две очереди, текущие не трогай', 'split', False),
 ('Удали из репозитория старые логи', 'delete', None), ('Подключи ещё одного советника, остальное как есть', 'add', False)]
import os
if os.environ.get('HOLDOUT'): CASES = HOLD
PP = json.load(open('/workspace/nox/agents/passport_prompt.json'))
SYS = PP['system']
SHOTS = []
for ph, v, sc in PP['shots']:
    SHOTS += [{'role': 'user', 'content': ph}, {'role': 'assistant', 'content': json.dumps({'verb': v, 'stop_current': sc}, ensure_ascii=False)}]
def ask(model, phrase):
    rq = urllib.request.Request('http://127.0.0.1:8793/v1/chat/completions', data=json.dumps({'model': model, 'messages': [{'role': 'system', 'content': SYS}] + SHOTS + [{'role': 'user', 'content': phrase}], 'max_tokens': 400, 'temperature': 0}).encode(), headers={'Content-Type': 'application/json'})
    r = json.loads(urllib.request.urlopen(rq, timeout=100).read()); tx = r['choices'][0]['message']['content']
    m = re.search(r'\{.*?\}', tx, re.S); return json.loads(m.group(0)), r.get('nox', {}).get('provider')
res = []; okv = oks = nv = ns = 0
for ph, v, sc in CASES:
    try: j, prov = ask('auto', ph); gv = str(j.get('verb', '')).lower(); gs = bool(j.get('stop_current'))
    except Exception as e: res.append({'phrase': ph, 'err': str(e)[:80]}); print('ERR', ph[:50], str(e)[:60], flush=True); time.sleep(3); continue
    nv += 1; a = gv == v; okv += a; b = True
    if sc is not None: ns += 1; b = gs == sc; oks += b
    res.append({'phrase': ph, 'want': v, 'got': gv, 'stop_want': sc, 'stop_got': gs, 'ok': a and b, 'by': prov}); print('OK ' if a and b else 'BAD', ph[:55], '|', v, gv, sc, gs, prov, flush=True); time.sleep(3)
tot = sum(1 for r in res if r.get('ok')); n = len(CASES)
out = {'n': n, 'answered': nv, 'full_ok': tot, 'share_full': round(tot / n, 2), 'verb_share': round(okv / max(nv, 1), 2), 'stop_share': round(oks / max(ns, 1), 2), 'cases': res, 'ts': int(time.time())}
json.dump(out, open('/workspace/nox/agents/eval_llm%s.json' % ('_hold' if os.environ.get('HOLDOUT') else ''), 'w'), ensure_ascii=False, indent=1); print('EVAL', {k: out[k] for k in ('n', 'answered', 'full_ok', 'share_full', 'verb_share', 'stop_share')})
