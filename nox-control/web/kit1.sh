#!/bin/bash
# kit1: проверка доступа S1 к Google Drive; при успехе скачивает 4 ZIP в новую папку и распаковывает (без применения)
D=/root/nox_kit_$(date +%s); df -h / | tail -1
for u in "https://drive.google.com/uc?export=download&id=1jxuLYe9tUI90UNllHI8vnYsKMOxWp7CR" "https://drive.usercontent.google.com/download?id=1jxuLYe9tUI90UNllHI8vnYsKMOxWp7CR&export=download&confirm=t"; do
  echo "HEAD $(curl -sI -m10 "$u" | head -1)"; done
pip install -q gdown 2>&1 | tail -1
mkdir -p $D/zip $D/out && cd $D/zip
i=0; for id in 1jxuLYe9tUI90UNllHI8vnYsKMOxWp7CR 14cYcdDuZUkuXrwjVlkkCAAIRvIwfUzPO 18nOeaWZ5G3H4qC6hYNRL3YhVvqC48UqD 1TmB0QR6fZGMakch7R7g05Op5d6QZrzGS; do
  i=$((i+1)); timeout 100 gdown -q "$id" -O kit_$i.zip 2>&1 | tail -2; done
ls -l; sha256sum *.zip
for z in *.zip; do unzip -tq $z | tail -1; done
cd ../out && for z in ../zip/*.zip; do unzip -qn $z; done
echo "DIR=$D"; ls -la | head -40; wc -c 00_START_HERE_RU.md 2>&1
