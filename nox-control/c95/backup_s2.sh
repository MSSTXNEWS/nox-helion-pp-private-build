#!/bin/bash
# Бэкап «старого НОКС» (S2) для переноса на новую модель. Только чтение исходников; пишет в /root/nox/backup_final (нужно ~6-8 ГБ, свободно 14 ГБ). Веса моделей НЕ входят (их можно скачать заново).
O=/root/nox/backup_final; mkdir -p $O; mkdir -p /root/nox/logs
exec 9>/root/nox/logs/bk.lock; flock -n 9 || { echo running; tail -3 /root/nox/logs/bk.log; exit 0; }
cat > /root/nox/bk_worker.sh <<'W'
O=/root/nox/backup_final; cd /root/nox
C=gzip; command -v zstd >/dev/null && C="zstd -T4 -3"
EXC="--exclude=*.log --exclude=__pycache__ --exclude=*.gguf --exclude=*.pyc --exclude=*.tmp --exclude=*.part --exclude=queue.jsonl.bak_*"
pk(){ n=$1; shift; ex=""; ls "$@" >/dev/null 2>&1 || return; tar -cf - $EXC --exclude=models --exclude=backup_final "$@" 2>/dev/null | $C > $O/$n.tar.${C%% *}; echo "$n $(du -h $O/$n.tar.* | tail -1)"; }
pk memory memory
pk knowledge knowledge
pk datasets datasets
pk lora lora
pk scripts scripts
pk state state
pk misc incoming_t750u coordination
mkdir -p $O/info; cp -p /root/nox/state/dispatcher/owner_orders.jsonl $O/info/ 2>/dev/null
(supervisorctl status; nvidia-smi -L; df -h /; python3 --version) > $O/info/system.txt 2>&1
cat > $O/KNOWLEDGE_TRANSFER.md <<'K'
# NOX (S2) -> перенос на новую модель (GLM-5.3 на S1)
Состав: memory (память, S03/Engram-индексы), knowledge (база знаний), datasets (корпуса/обучающие данные), lora (адаптеры Qwen3.5-9B: привязаны к старой модели, как данные дистилляции, не как веса),
scripts (скрипты НОКС), state (состояние диспетчера, личность/ядро, NOX_SELF), misc, info/owner_orders.jsonl (журнал приказов).
Переносимое на любую модель: память, знания, датасеты, системный промпт/личность, судьи-промпты, журналы.
Не переносимое: LoRA-адаптеры и Engram-веса под DeepSeek (пересобрать/дистиллировать).
Порядок восстановления: 1) memory+knowledge -> S1:/root/nox, 2) личность и системный промпт (state) -> промпт GLM, 3) datasets -> S2 для дообучения, 4) экзамен НОКС (код, веб, рассуждения, русский, личность, память).
K
cd $O && sha256sum *.tar.* KNOWLEDGE_TRANSFER.md > SHA256SUMS; du -sh $O; echo BK_DONE $(date)
W
nohup setsid bash -c 'exec 9>&-; bash /root/nox/bk_worker.sh' > /root/nox/logs/bk.log 2>&1 < /dev/null &
sleep 40; cat /root/nox/logs/bk.log; df -h / | tail -1
