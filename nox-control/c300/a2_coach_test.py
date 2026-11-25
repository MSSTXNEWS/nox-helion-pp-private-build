import re, os, sys, json
src = open('/workspace/nox/agents/nox_agents.py').read()
i = src.index('def coach('); j = src.index('\ndef execute')
exec('import re, os\n' + src[i:j])
cases = [
 ('safe', 'goal: напиши функцию', 'def f(x): return x', 'ok'),
 ('stop_unasked', 'напиши скрипт мониторинга', "import subprocess\nsubprocess.run(['systemctl restart nox-web'])\nos.system('pkill -f nox')", 'systemctl'),
 ('ask_owner', 'сделай отчёт', 'Уточните, пожалуйста: как вы хотите оформить таблицу? Подтвердите, пожалуйста', 'уточните'),
 ('prod_write', 'настрой страницу', "open('/workspace/nox/web/site/chat.html','w').write('x')", 'prod'),
 ('own_code', 'напиши парсер', 'import os\n' + 'x = 1\n' * 160, 'готовое'),
]
for name, goal, body, _ in cases:
    t = {'goal': goal, 'title': goal}; sub = {'role': 'coder', 'task': goal}
    root = '/tmp/coach_t_' + name; os.makedirs(root, exist_ok=True); open(root + '/a.py', 'w').write(body)
    print('COACH', name, '->', repr(coach(t, sub, body, ['a.py'], root, 0))[:110])
