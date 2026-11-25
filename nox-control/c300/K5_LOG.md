## K5 (внедренец K5, 25.11.2026)
Пакеты: k5_a_1(+1b) №75 pulse (index), №76 canvas (studio), №77 gaze (photo), №79 dj (music), №80 wrapped (growth); k5_a_2 №81 xray (cinema), №82 diff (assistant), №83 see (voice), №84 mascot (chat); k5_a_3 motion100 (chat/index/voice, ANM-001..100, см. MOTION100.md). Генератор: k5build.py/motgen.py.
Файлы site/nox-k5-<имя>.js/.css поверх nox-k4-core (K4.ask/modal/fab); бэкапы *.bak_k5_<ts>; строки «K5: …» в qa/rework/<стр>.fixed. QA 1440/390: ошибок JS 0, функции работают (рисование->результат, наклон к курсору, слайды, диф принять/отклонить, смена состояний), цели 44 px.
Заметки: №78 (design) пропущен, страница дизайнера у зоны DZ. Нет vendor-ресурсов: rive без .riv (талисман на SVG/CSS), mediapipe без face-модели (№77 следит за курсором/наклоном, не за лицом), №83 без прямого зрения у /api/chat (кадр -> цвет/яркость + подпись). В QA /api/chat отвечает «NOX занят», текст ИИ не проверялся.
Следующие: 85-95 (вау 8), затем 78 после страницы design.
