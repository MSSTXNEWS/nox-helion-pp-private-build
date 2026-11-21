#!/bin/bash
# реранкер + репозиторий на S1 + пакеты голоса; всё в фоне, лог /root/nox/dl/logs/deps.log
D=/root/nox/dl; L=$D/logs/deps.log
pgrep -f deps_worker >/dev/null && { echo running; exit 0; }
cat > $D/deps_worker.sh <<'W'
#!/bin/bash
D=/root/nox/dl; export HF_HUB_ENABLE_HF_TRANSFER=1
( hf download BAAI/bge-reranker-v2-m3 --local-dir $D/hf/reranker > $D/logs/hf_reranker.log 2>&1 && echo "HF_OK reranker" >> $D/logs/hf_all.log || echo "HF_FAIL reranker" >> $D/logs/hf_all.log ) &
( apt-get install -y -qq ffmpeg alsa-utils >/dev/null 2>&1; echo "APT rc=$?" ) &
R=/root/nox/repo
if [ -d $R/.git ]; then git -C $R pull -q; else git clone -q --depth 1 https://github.com/MSSTXNEWS/nox-helion-pp-private-build $R; fi
echo "REPO rc=$? $(ls $R/nox-control 2>/dev/null | head -3 | tr '\n' ' ')"
wait
cd $R/nox-control/voice && SKIP_TTS=1 bash install_deps.sh 2>&1 | tail -8
pip3 install -q --break-system-packages coqui-tts torch --index-url https://download.pytorch.org/whl/cpu 2>&1 | tail -2
pip3 install -q --break-system-packages coqui-tts 2>&1 | tail -2
echo DEPS_DONE
W
chmod +x $D/deps_worker.sh; nohup $D/deps_worker.sh > $L 2>&1 &
sleep 40; tail -12 $L | cut -c1-200; bash /root/nox/repo/nox-control/c120/dl_status_s1.sh 2>/dev/null | head -0
cat $D/logs/hf_all.log; du -sh $D/hf/* 2>/dev/null
