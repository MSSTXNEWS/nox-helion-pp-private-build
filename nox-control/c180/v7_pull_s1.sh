#!/bin/bash
D=/root/nox/dl/v7; mkdir -p $D; cd $D
pip list 2>/dev/null | grep -qi gdown || pip install -q gdown --break-system-packages 2>&1 | tail -1
gdown -q "https://drive.google.com/uc?id=1z_hAWjxeVK3-G-mR4MuGptQWHkPKTanV" -O core.zip; gdown -q "https://drive.google.com/uc?id=1tPH-fW5Hi-2TeHMfuKNmwPOVYgHKwSdu" -O hotfix.zip
ls -l; rm -rf core hotfix; mkdir core hotfix; unzip -q -o core.zip -d core; unzip -q -o hotfix.zip -d hotfix
echo "== core top"; ls core | head -30; echo "== hotfix"; find hotfix -maxdepth 2 | head -20
echo "== HOTFIX_NOW"; f=$(find core hotfix -name HOTFIX_NOW.md | head -1); echo $f; head -c 1800 "$f"
echo "== DEPLOY"; find core -path "*DEPLOY*" -type f | head
