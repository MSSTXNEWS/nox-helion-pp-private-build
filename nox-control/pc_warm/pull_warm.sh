#!/bin/bash
# Тёплые веса: ПК -> RAM сервера (/dev/shm, не диск). Использование: pull_warm.sh <путь внутри MODELS> ; докачка (-C -), проверка размера.
set -e
PC=${PC:-http://100.84.111.36:8765}; DST=/dev/shm/nox_warm; mkdir -p $DST
rel="$1"; [ -n "$rel" ] || { echo "usage: pull_warm.sh llm/Qwen3-30B-A3B-Q4_K_M.gguf"; exit 2; }
out="$DST/$(basename "$rel")"
want=$(curl -sSI -m 15 "$PC/$rel" | tr -d '\r' | awk 'tolower($1)=="content-length:"{print $2}')
[ -n "$want" ] || { echo "ПК недоступен или файла нет: $PC/$rel"; exit 3; }
avail=$(df --output=avail -B1 $DST | tail -1); [ "$avail" -gt "$((want+5368709120))" ] || { echo "мало места в /dev/shm"; exit 4; }
curl -L -C - --retry 5 -o "$out" "$PC/$rel"
[ "$(stat -c %s "$out")" = "$want" ] && echo "WARM_OK $out $want" || { echo "размер не совпал"; exit 5; }
