# Сборка моделей NOX Cinema Assist из частей Google Drive

Drive ограничивает размер одного файла 100 МиБ. Поэтому три больших веса лежат частями по 90 МиБ, без сжатия и потери байтов.

1. Скачайте все файлы с суффиксом `.part0001`, `.part0002` и далее в соответствующую Drive-папку: `ASR_FASTER_WHISPER_SMALL`, `MT_OPUS_ES_RU_APACHE` или `TTS_XTTS_V2_NONCOMMERCIAL`.
2. Сохраните рядом `NOX_CINEMA_MODEL_MANIFEST.json` и `assemble_cinema_models.py`.
3. Запустите `python assemble_cinema_models.py` из папки с этими тремя модельными папками.
4. Скрипт соберёт `model.bin`, `pytorch_model.bin` и `model.pth` и проверит размер и полный SHA-256. При неполном/повреждённом наборе он сообщит отсутствующие части и оставит исходные части на месте.

Малые конфиги, tokenizer и SentencePiece лежат рядом в Drive. XTTS-веса лицензированы CPML для некоммерческого использования; перед коммерческим применением подберите другой движок.
