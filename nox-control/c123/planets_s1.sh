#!/bin/bash
# S1: текстуры планет Solar System Scope (CC BY 4.0, данные NASA) -> /root/nox/web/vendor/nox-planets/
# Источники по порядку: 1) www.solarsystemscope.com/textures/download/<файл>; 2) зеркало на GitHub (homer-jay/solar-system-textures, имена ищутся через GitHub API, в README зеркала указаны SSS и CC BY 4.0).
# Каждый файл проверяется (сигнатура JPEG/PNG, размер); пишутся manifest.json (что реально лежит), LICENSE-CC-BY-4.0.txt и ATTRIBUTION.txt. Ничего не удаляет; уже скачанное пропускает.
D=${NOX_PLANETS:-/root/nox/web/vendor/nox-planets}; mkdir -p "$D"; cd "$D" || exit 1
echo "probe sss: $(curl -sI -m 15 -o /dev/null -w '%{http_code}' https://www.solarsystemscope.com/textures/download/2k_mars.jpg) | probe gh-api: $(curl -sI -m 15 -o /dev/null -w '%{http_code}' https://api.github.com/repos/homer-jay/solar-system-textures) | probe raw: $(curl -sI -m 15 -o /dev/null -w '%{http_code}' https://raw.githubusercontent.com/homer-jay/solar-system-textures/HEAD/README.md)"
python3 - "$D" <<'PY'
import sys, os, json, urllib.request, re
D = sys.argv[1]; os.chdir(D)
WANT = ['2k_mercury.jpg', '2k_venus_surface.jpg', '2k_earth_daymap.jpg', '2k_moon.jpg', '2k_mars.jpg', '2k_jupiter.jpg', '2k_saturn.jpg', '2k_saturn_ring_alpha.png', '2k_uranus.jpg', '2k_neptune.jpg']
UA = {'User-Agent': 'nox-web-installer/1.0'}
def get(url, timeout=60):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()
def valid(b, name):
    if len(b) < 20000: return False
    return b[:3] == b'\xff\xd8\xff' if name.endswith('.jpg') else b[:4] == b'\x89PNG'
tree = None
def mirror_tree():
    global tree
    if tree is None:
        try:
            j = json.loads(get('https://api.github.com/repos/homer-jay/solar-system-textures/git/trees/HEAD?recursive=1', 30))
            tree = [t['path'] for t in j.get('tree', []) if t.get('type') == 'blob']
        except Exception as e:
            print('mirror tree FAIL:', e); tree = []
    return tree
def mirror_pick(name):
    key = re.sub(r'^2k_|\.(jpg|png)$', '', name)  # mercury, venus_surface, earth_daymap, saturn_ring_alpha ...
    short = key.split('_')[0]
    ext = name.rsplit('.', 1)[1]
    c = [p for p in mirror_tree() if p.lower().endswith('.' + ext) and short in os.path.basename(p).lower()]
    if 'ring' in key: c = [p for p in c if 'ring' in p.lower()]
    else: c = [p for p in c if 'ring' not in p.lower() and 'cloud' not in p.lower() and 'night' not in p.lower() and 'normal' not in p.lower() and 'spec' not in p.lower() and 'bump' not in p.lower()]
    c.sort(key=lambda p: (0 if '2k' in p.lower() else 1, len(p)))
    return c[0] if c else None
res = {}
for n in WANT:
    if os.path.isfile(n) and valid(open(n, 'rb').read(), n):
        res[n] = 'уже есть (%d КБ)' % (os.path.getsize(n) // 1024); continue
    got = None
    try:
        b = get('https://www.solarsystemscope.com/textures/download/' + n)
        if valid(b, n): open(n, 'wb').write(b); got = 'solarsystemscope.com %d КБ' % (len(b) // 1024)
    except Exception as e: sss = str(e)[:60]
    if not got:
        p = mirror_pick(n)
        if p:
            try:
                b = get('https://raw.githubusercontent.com/homer-jay/solar-system-textures/HEAD/' + p.replace(' ', '%20'), 120)
                if valid(b, n): open(n, 'wb').write(b); got = 'зеркало GitHub %s %d КБ' % (p, len(b) // 1024)
            except Exception as e: got = None
    if not got and not mirror_tree():  # GitHub API недоступен: угадываем типичные пути в зеркале
        for pre in ['', 'textures/', '2k/', 'images/', 'img/', 'assets/', 'public/textures/', 'src/textures/']:
            for nm in (n, n.replace('2k_', '')):
                try:
                    b = get('https://raw.githubusercontent.com/homer-jay/solar-system-textures/HEAD/' + pre + nm, 60)
                    if valid(b, n): open(n, 'wb').write(b); got = 'зеркало GitHub %s%s %d КБ' % (pre, nm, len(b) // 1024); break
                except Exception: pass
            if got: break
    res[n] = got or 'НЕ СКАЧАЛОСЬ (останется процедурная текстура)'
# файлы, уже лежащие в сборке (уменьшенные Земля/Луна) тоже в манифест
have = sorted(f for f in os.listdir('.') if f.lower().endswith(('.jpg', '.png')))
json.dump({'files': have, 'source': 'Solar System Scope, CC BY 4.0'}, open('manifest.json', 'w'), ensure_ascii=False)
for n, v in res.items(): print(' ', n, '->', v)
print('manifest:', ' '.join(have))
PY
cat > ATTRIBUTION.txt <<'T'
Текстуры планет: Solar System Scope (https://www.solarsystemscope.com/textures/), основаны на данных NASA.
Лицензия: Creative Commons Attribution 4.0 International (CC BY 4.0), https://creativecommons.org/licenses/by/4.0/
Разрешено использование, адаптация и распространение, в том числе в коммерческих целях, при указании авторства «Solar System Scope».
Изменения: файлы без изменений (как скачаны); меньшие по размеру копии Земли и Луны в сборке уменьшены вдвое.
Ссылка на зеркало, если основной сайт был недоступен: https://github.com/homer-jay/solar-system-textures
T
cat > LICENSE-CC-BY-4.0.txt <<'T'
Creative Commons Attribution 4.0 International (CC BY 4.0)
Полный текст: https://creativecommons.org/licenses/by/4.0/legalcode
Кратко: вы можете делиться (копировать и распространять) и адаптировать материал в любых целях, включая коммерческие, при условии указания авторства
(Solar System Scope), ссылки на лицензию и пометки о внесённых изменениях.
T
ls -la "$D" | awk '{print $5, $9}' | tail -n +4 | tr '\n' ';'; echo
