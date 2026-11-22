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
