#!/bin/bash
# S1: скачать с публичных ссылок Google Диска (parallel) в /root/nox/dl/drive и распаковать в /root/nox/dl/drive/x/<имя>
D=/root/nox/dl/drive; mkdir -p $D/x; cd $D
pip3 install -q --break-system-packages gdown 2>&1 | tail -1
declare -A F=(
 [V25_FULL_WEB_r3.zip]=1HOnb5tWW558rMricTth30zZJq0dnnboF
 [V21_24_LIBS.zip]=1D1Nk-kT8Zn87nhUc1jdz1M1NfcyJuEol
 [V21_RUNTIME_VENDOR_20.zip]=1Ymr43KE52nhKZKrU8Th0ioqf4z4B-FDu
 [V19_GLASS_INTERFACE.zip]=1XUzluK-6JhjXeMV9EZhgTXdKNxn4ELEp
 [V19_CINEMATIC_VISUAL.zip]=1LEYtr3A2c1f5uXchBa2HMhlpCUQf5hcT
 [npm_modules_with_dependencies.zip]=1h1hXo-QKbsmM2jq37wPqSBPqF0b19tQW
 [WOW_MISSING_THREE.zip]=1HWkOZKWfheqgAgGM0rz4JE_w5PN18Q-n
 [nox-universe-v19.js]=1bVXziAQ408Yu7Hj4Brr2z39owbBpOdZ0
 [nox-universe-v19.css]=1dpk4NVdUyNTJT8b7w50wb6xV5EVnUpZn
 [nox-owner-director-v20.js]=1d9ONnkEg5-MwLnRZIE7IMRuab0naA_B5
 [nox-owner-director-v20.css]=1b36U1c3kVczHaoZ8kzDJppRW2JcyktrQ )
for n in "${!F[@]}"; do ( gdown -q "https://drive.google.com/uc?id=${F[$n]}" -O "$n" && echo "OK $n $(stat -c%s $n)" || echo "FAIL $n" ) & done; wait
for z in *.zip; do [ -f "$z" ] && { mkdir -p x/${z%.zip}; unzip -q -o "$z" -d x/${z%.zip} 2>&1 | tail -1; }; done
echo "== tree"; for d in x/*; do echo "$d: $(find $d -type f | wc -l) файлов, $(du -sh $d | cut -f1)"; done
ls -la | head -20
