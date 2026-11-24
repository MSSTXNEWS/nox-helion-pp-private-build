#!/bin/bash
# b_progress5.sh: чтение API sun_adapter/imgsvc, наличие registry.json, дозапись блока B в PROGRESS.md (append)
set -u
W=/workspace/nox
echo "== sun_adapter source"
F=$(grep -rl "8097" $W --include=*.py 2>/dev/null | grep -v venv | head -5); echo "$F"
for f in $F; do echo "-- $f"; grep -n "route\|@app\|add_api\|def \|path ==\|startswith(\"/" "$f" | head -40; done
echo "== imgsvc 8500"
curl -s --max-time 5 http://127.0.0.1:8500/health | head -c 300; echo
echo "== registry"; ls -la $W/web/site/qa/registry.json 2>/dev/null || echo "no registry.json"
echo "== flags"; ls -la $W/state/ 2>/dev/null | head
TS=$(date -u +%FT%TZ)
cat >> $W/ops/controller/PROGRESS.md <<MD

## ВРЕМЯ B $TS
- Голос: патч _safe_accent в c300_voice/voice2/tts2_server.py (бэкап tts2_server.py.bak_b_2) - убирает лишний «+» в начале слова («+яйца»). Сервис не перезапускался: эффект появится после рестарта tts2.
- Голос по test10: «на 85%» -> «на восемьдесят пять процентов» проверено. Открытое: T7 в SSML-выводе показан только первым предложением (не подтверждено, проверить на аудио).
- Скриншоты voice.html 1440x900 и 390x844 сделаны (qa/voice2/voice_final_*.png). Ошибок страницы 0. Проверка всех страниц по HTTP: qa/batch2/report_http.json.
- Диск 15 ГБ свободно: гейт владельца (>=15 ГБ после установки) не позволяет ставить ACE-Step (~22 ГБ), Qwen-Image-Edit GGUF, Z-Image-Turbo, gpt-researcher-стек и новые разделы без освобождения места. Установки не выполнялись.
- Голосовые кандидаты (T-one, Qwen3-TTS, CosyVoice3, Fish S2, pipecat) не оценены по диску: до освобождения места оценка только по размеру, без загрузки.
- studio.html и photo.html не ссылаются на :8500 и :8097: подключение к sun_adapter не сделано, нужен API sun_adapter (см. лог b_progress5).
- Режим: живой контур не трогал; флагов в state/ нет, поэтому флаг для правок не создан.
MD
echo "appended PROGRESS.md at $TS"
