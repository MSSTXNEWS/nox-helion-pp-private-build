"""NOX voice: STT (faster-whisper) + TTS (XTTS/Piper) серверы и голосовой цикл. Серверы и тесты - только stdlib;
faster-whisper/numpy/TTS/piper подключаются лениво, /health честно показывает, что реально доступно."""
PORT_STT = 8093   # 8091 занят nox-bridge, 8092 зарезервирован рядом; 8080-8083/8098 тоже заняты
PORT_TTS = 8094
