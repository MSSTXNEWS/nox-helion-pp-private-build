# S1 (61825960) — текущая рабочая конфигурация, 22.11.2026 (сессия c300)

Не откатывать без замера. Всё проверено живыми тестами чата.

- GLM-5.3-Flash UD-Q4_K_XL, /dev/shm/glm53f, свежий llama.cpp: /root/nox/llama.cpp-f
- /root/nox/start_glm.sh (автоподбор flash_ab4): `taskset -c 0-23 nice 19 -t 24 -tb 24 -ngl 40 -ot exps=CPU --no-op-offload --parallel 2 -c 16384 -ub 512 -b 2048 --reasoning off`
  - tg 5.73 ток/с (было 2.6). ngl 44 / 99 — OOM на 16 ГБ. t27 хуже t24. ngram-spec не даёт прироста.
  - --no-op-offload обязателен: без него pp ~3 ток/с (эксперты гоняются по PCIe3 x8).
  - ядра 24+ не трогать: на них Qwen3-30B (:8083, taskset 26-33). Перегруз CPU (>27 квота cgroup) убивает быстрый чат.
- Быстрый тир: Qwen3-30B-A3B-Instruct-2507 Q4_K_M :8083 (memfd), запасной Qwen3-4B.
- web_server.py (:8091) — полная версия (виджеты /api/sys, deep напрямую в :8081, keepalive). НЕ заменять копией s1web/web_server.py.
  - Режим «Глубоко» теперь берёт память S03 (MemoryLayer, факты в последнее сообщение, после ответа after_reply).
- Prime: развернуты wow7/{CON,PER,EMO,WORLD,CTX} из dl/v7/core/nox_wow — все части личности подключены.
- boot_s1.sh: GLM через start_glm.sh, шлюз NOX_UPSTREAM=8099 + таймауты, web_server не перезатирается.
- Открыто: проверка STOP/голоса при перебивании, LoRA-кандидаты из личных фактов, испанский, узкие правила fact_extract.

## Обновление 22.11 ~15:15 UTC (c300)
- web_server.py на S1 = СЛИЯНИЕ: c300 (deep напрямую в :8081 + память S03 + id_slot 0 + /api/sys + /api/feedback) + /api/pc-metrics и /api/health от c173. Для restore правьте этот файл; не заменяйте s1web/web_server.py (там нет deep и памяти).
- chat.html обязан подключать ./nox_mode.js (👍/👎 через /api/feedback, компактные интервалы, виджеты).
- qs6/mem_filter.py — фильтр мусора S03 (логи, пути, квитанции, хэши). Подключён в deep (web_server) и в gateway_prime memory().
- TTS: NOX_PIPER_MODEL_RU был испанским (es_ES-davefx), отсюда белиберда. Теперь ru_RU-ruslan (и в boot_s1.sh); textproc: NOX → «Нокс».
- Подбор флагов GLM ведёт c320 (flashopt), c300 GLM не трогает. Лучший замер c300: taskset 0-23, -ngl 40 -t 24 --parallel 2 -c 16384 → tg 5.73.
- ВАЖНО для c320: без taskset и с -t 26 GLM забирает процессор у быстрой модели (:8083 на ядрах 26-33), нагрузка 108 при квоте ~27, быстрый чат 10 с вместо 2-3. Итоговый вариант должен оставлять ядра 26-33 свободными.

## Обновление 22.11 ~20:30 UTC (c300) — внедрение W001–W100 (применимое)
- W061–W064 MTP: свежий llama.cpp (/root/nox/llama.cpp-g, 5bacb7c) + `--spec-type draft-mtp --spec-draft-n-max 3`, `-ngl 36` (на 38–40 MTP не влезает в 16 ГБ). tg 6.52 (без MTP 5.64), принятие ~70%. start_glm.sh обновлён.
- W038/W070: embed_server перенесён на ядра 34-39 (nice 10), в onstart.sh тоже. Ядра 26-33 — только быстрая модель.
- Быстрый режим: web_server шлёт «Быстро» напрямую в :8083 со своей душой и отфильтрованной памятью (NOX_FAST_DIRECT=1), без ядра с телеметрией. Шлюз :8082 с NOX_CORE=1 остаётся для других клиентов.
- «Ритуальные фразы» из души вырезаются в web_server (модель повторяла их дословно).
- c320 вариант (-ngl 32 -t 24 -np 4 -kvu q4_0) дал tg 3.94 — хуже, откатан.
