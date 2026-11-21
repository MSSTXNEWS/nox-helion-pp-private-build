#!/bin/bash
# параллельная загрузка всего нужного для чата на S1 (npm, HF, GitHub). Запуск в фоне, логи в /root/nox/dl/logs
D=/root/nox/dl; mkdir -p $D/{npm,hf,gh,logs}; cd $D; rm -f $D/logs/hf_all.log
if pgrep -f dl_all_worker >/dev/null; then echo already_running; exit 0; fi
cat > $D/dl_all_worker.sh <<'W'
#!/bin/bash
D=/root/nox/dl
which npm >/dev/null 2>&1 || apt-get install -y -qq npm >/dev/null 2>&1
pip3 install -q --break-system-packages huggingface_hub hf_transfer 2>&1 | tail -1
export HF_HUB_ENABLE_HF_TRANSFER=1
# --- npm: точные версии с Диска + кит
( cd $D/npm; for p in three@0.187.0 postprocessing@6.39.6 gsap@3.15.1 motion@14.14.0 tsparticles@4.6.0 vanta@0.5.24 lottie-web@5.13.0 ogl pixi.js swiper @shoelace-style/shoelace @floating-ui/dom @tabler/icons photoswipe pdfjs-dist cytoscape wavesurfer.js @xterm/xterm driver.js @rive-app/canvas @fullcalendar/core sortablejs onnxruntime-web @ricky0123/vad-web; do
  ( npm pack $p --silent >> $D/logs/npm.log 2>&1 && echo "OK $p" >> $D/logs/npm.log || echo "FAIL $p" >> $D/logs/npm.log ) &
done; wait; echo NPM_DONE >> $D/logs/npm.log ) &
# --- HF: параллельно
dl(){ n=$1; shift; ( hf download "$@" --local-dir $D/hf/$n > $D/logs/hf_$n.log 2>&1 && echo "HF_OK $n" >> $D/logs/hf_all.log || echo "HF_FAIL $n" >> $D/logs/hf_all.log ) & }
dl qwen3_4b unsloth/Qwen3-4B-Instruct-2507-GGUF Qwen3-4B-Instruct-2507-Q4_K_M.gguf
dl whisper_small Systran/faster-whisper-small
dl whisper_large_v3_turbo deepdml/faster-whisper-large-v3-turbo-ct2
dl bge_m3 BAAI/bge-m3
dl e5_small intfloat/multilingual-e5-small
dl rubert_emotion Aniemore/rubert-tiny2-russian-emotion-detection
dl smart_turn pipecat-ai/smart-turn-v3
dl xtts coqui/XTTS-v2
dl piper_ru rhasspy/piper-voices --include "ru/ru_RU/*/medium/*" --include "es/es_ES/*/medium/*"
dl silero_vad snakers4/silero-vad
# --- GitHub
( cd $D/gh; for r in KoljaB/RealtimeVoiceChat pipecat-ai/smart-turn QuentinFuxa/WhisperLiveKit remsky/Kokoro-FastAPI t0mmy-gh/mnemosyne; do
  ( git clone -q --depth 1 https://github.com/$r >> $D/logs/gh.log 2>&1 && echo "OK $r" >> $D/logs/gh.log || echo "FAIL $r" >> $D/logs/gh.log ) &
done; wait; echo GH_DONE >> $D/logs/gh.log ) &
wait; echo ALL_FINISHED >> $D/logs/hf_all.log
W
chmod +x $D/dl_all_worker.sh; nohup $D/dl_all_worker.sh > $D/logs/worker.log 2>&1 &
sleep 20; echo started; tail -3 $D/logs/*.log | cut -c1-160; df -h /root | tail -1
