cd /workspace/nox/web/site/qa/rework
cat >> chat.fixed <<'F'
Добавлено (S1, вау): голосовой орб three-шейдер в шапке (9.4) - реагирует на микрофон (Web Audio Analyser + silero VAD из vendor/nox-x/vad, грузится при первом нажатии на орб), на поток токенов и «думает»; фон реагирует на громкость через --nox-voice на #space/#dust (F1); поток мыслей - GPU-частицы three за лентой, плотность от активности (17.1); liquid-glass (kwlck/liquid-glass-web, MIT) на шапке и поле ввода (2.4). Файлы: nox-chat-fx.js, nox-fx-lg.css.
F
cat >> index.fixed <<'F'
Добавлено: liquid-glass (2.4) на приветствии, событиях и плитках (nox-home-fx.js, vendor/nox-liquid-glass). Бэкапы index.html.bak_s1_*, chat.html.bak_s1_*.
F
tail -2 chat.fixed | cut -c1-80
