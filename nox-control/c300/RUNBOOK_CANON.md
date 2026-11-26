# RUNBOOK канона NOX (K1)
Демон: supervisorctl status nox_canon (рестарт: supervisorctl restart nox_canon). Код: /workspace/nox/canon/canon.py (источник: nox-control/c300/bundles/canon/).
Команды: python3 -I canon.py disk|backup|drive|passport|birth|selfnow|morning|evening|exam|hunger|unknown|feelings|verify|journal|static
Что где: state/core/{passport.json,genesis_chain.jsonl,self_now.json,hunger.json,unknown_map.json,hunt_requests.json,weekly_exam.json,journal.jsonl,disk_low.flag}; state/mind/{morning,evening}_brief_v5.json; canon/soul/soul_hNN.tgz (24 слота, локально), soul_cfg_hNN.tgz[.age] (конфиги, на Диск при рабочем rclone).
Восстановление души: 1) взять soul_hNN.tgz нужного часа (или копию с Диска; .age расшифровать: age -d -i <приватный ключ> файл.age > файл.tgz); 2) tar -tzf для проверки, MANIFEST.json содержит sha256 всех файлов; 3) распаковать во временную папку, сверить sha256, затем cp нужных файлов на место (passport.json, genesis_chain.jsonl, ledger); 4) python3 -I canon.py verify должен вернуть true. Автотест: после каждого бэкапа restore_test пишет restore_ok в canon/soul_hourly_ok.json.
Диск <15 ГБ: canon/disk_guard.log + state/core/disk_low.flag; сам ничего не удаляет.
Рождение: state/core/birth_evidence.json {delta_sha, reload_ok, test_pass} -> canon.py birth.
