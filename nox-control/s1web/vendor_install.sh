#!/bin/bash
# S1: распаковать npm-архивы (.tgz из npm pack) в WEB/vendor/<имя>/ + локальные шрифты woff2 (без CDN).
# Идемпотентно. Env: NOX_DL (по умолч. /root/nox/dl/npm), NOX_VENDOR (по умолч. /root/nox/web/vendor).
# Также берёт готовые пакеты из наборов Диска (/root/nox/dl/drive/x/*/packages/*.tgz), если такого имени ещё нет.
# Запуск ПОСЛЕ s1_web_deploy.sh (тот подменяет /root/nox/web целиком). Ничего не удаляет: каждая либа кладётся в свою папку поверх.
DL=${NOX_DL:-/root/nox/dl/npm}; OUT=${NOX_VENDOR:-/root/nox/web/vendor}
mkdir -p "$DL" "$OUT"; cd "$DL" || exit 1
# шрифты и GlassKit (MIT, чистый CSS): npm pack на S1 (если ещё нет); не получилось - честно пишем и идём дальше
for f in @fontsource/inter @fontsource/jetbrains-mono @fontsource/manrope @jungherz-de/glasskit; do
  b=$(echo "$f" | sed 's#^@##; s#/#-#')
  if ! ls "$b"-*.tgz >/dev/null 2>&1; then
    if command -v npm >/dev/null 2>&1; then timeout 120 npm pack "$f" >/dev/null 2>&1 && echo "pack ok $f" || echo "pack FAIL $f"; else echo "npm не найден: $f пропущен"; fi
  fi
done
python3 - "$DL" "$OUT" <<'PY'
import sys, os, re, json, tarfile, shutil
dl, out = sys.argv[1], sys.argv[2]
MAP = {'@shoelace-style/shoelace': 'shoelace', '@floating-ui/dom': 'floating-ui-dom', '@tabler/icons': 'tabler-icons',
       '@xterm/xterm': 'xterm', '@fullcalendar/core': 'fullcalendar-core', '@ricky0123/vad-web': 'vad-web',
       '@rive-app/canvas': 'rive-canvas', '@fontsource/inter': 'fontsource-inter',
       '@jungherz-de/glasskit': 'glasskit', '@fontsource/jetbrains-mono': 'fontsource-jetbrains-mono', '@fontsource/manrope': 'fontsource-manrope'}
ok, bad = [], []
import glob
# источники: сначала npm-архивы владельца (dl/npm), затем готовые наборы Диска (dl/drive/x/*/packages) - только то, чего ещё нет (без дублей vendor)
srcs = [(dl, False)] + [(d, True) for d in sorted(glob.glob(os.path.join(os.path.dirname(dl), 'drive', 'x', '*', 'packages')))]
items = [(os.path.join(d, fn), fn, dr) for d, dr in srcs if os.path.isdir(d) for fn in sorted(os.listdir(d)) if fn.endswith('.tgz')]
for p, fn, from_drive in items:
    try:
        with tarfile.open(p) as t:
            name = json.load(t.extractfile('package/package.json'))['name']
            d = os.path.join(out, MAP.get(name, re.sub(r'^@', '', name).replace('/', '-')))
            if from_drive and os.path.isfile(os.path.join(d, '.nox-from')): continue
            if os.path.isfile(os.path.join(d, '.nox-from')) and open(os.path.join(d, '.nox-from')).read() == fn:
                ok.append(name + ' (уже)'); continue
            os.makedirs(d, exist_ok=True)
            for m in t.getmembers():
                if not m.name.startswith('package/') or not (m.isfile() or m.isdir()): continue
                rel = m.name[len('package/'):]
                if not rel or '..' in rel.split('/'): continue
                m.name = rel; t.extract(m, d)
            open(os.path.join(d, '.nox-from'), 'w').write(fn)
            ok.append(name)
    except Exception as e:
        bad.append('%s: %s' % (fn, e))
# шрифты: @font-face на локальные woff2
def face(fam, pkg, subs, wts, ital='normal'):
    css = []
    for sub in subs:
        rng = {'cyrillic': 'U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116', 'latin': 'U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD'}[sub]
        for w in wts:
            f = '%s/files/%s-%s-%s-%s.woff2' % (pkg, pkg.split('fontsource-')[1], sub, w, ital)
            if os.path.isfile(os.path.join(out, f)):
                css.append("@font-face{font-family:'%s';font-style:%s;font-display:swap;font-weight:%s;src:url(../%s) format('woff2');unicode-range:%s}" % (fam, ital, w, f, rng))
    return css
css = face('Inter', 'fontsource-inter', ['cyrillic', 'latin'], [400, 500, 600, 700]) + \
      face('Manrope', 'fontsource-manrope', ['cyrillic', 'latin'], [300, 400, 500, 600, 700, 800]) + \
      face('JetBrains Mono', 'fontsource-jetbrains-mono', ['cyrillic', 'latin'], [400, 500])
os.makedirs(os.path.join(out, 'fonts-wow'), exist_ok=True)
open(os.path.join(out, 'fonts-wow', 'fonts.css'), 'w').write('/* локальные шрифты (fontsource, OFL-1.1), без CDN */\n' + '\n'.join(css) + '\n')
print('unpacked:', len(ok), '|', ', '.join(ok))
if bad: print('ERR:', '; '.join(bad))
print('font-faces:', len(css))
# контроль: файлы, которые реально использует сборка
need = ['three/build/three.module.js', 'three/build/three.core.js', 'postprocessing/build/index.js', 'motion/dist/motion.js', 'tsparticles/tsparticles.bundle.min.js',
        'lottie-web/build/player/lottie.min.js', 'wavesurfer.js/dist/wavesurfer.esm.js', 'driver.js/dist/driver.js.mjs', 'driver.js/dist/driver.css',
        'shoelace/cdn/shoelace-autoloader.js', 'shoelace/cdn/themes/dark.css', 'tabler-icons/icons/outline/microphone.svg', 'swiper/swiper-bundle.min.mjs', 'swiper/swiper-bundle.min.css', 'glasskit/glasskit.min.css', 'fonts-wow/fonts.css']
miss = [n for n in need if not os.path.isfile(os.path.join(out, n))]
print('MISSING:' if miss else 'контроль путей: OK (%d)' % len(need), ' '.join(miss))
PY
du -sh "$OUT" 2>/dev/null | tail -1
