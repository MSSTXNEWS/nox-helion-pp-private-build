#!/bin/bash
# Доставка веб-сборки NOX на сервер: скачать -> sha256 -> распаковать в /opt/nox-web.new -> атомарно переключить.
# Использование: deploy_web.sh <sha256 архива> <url> [url2 ...]   (несколько url = части, склеиваются по порядку)
# Архив: tar.xz (или tar.zst, если есть zstd). Идемпотентно: если sha уже развёрнут (/opt/nox-web/.deploy_sha) - выход.
# НЕ трогает: Engram memfd, nox_lean_fallback, state/slots, прочие каталоги. Старую версию не удаляет (nox-web.prev.<ts>).
set -u
SHA="${1:-}"; shift || true
[ -z "$SHA" ] || [ $# -eq 0 ] && { echo "usage: deploy_web.sh <sha256> <url> [url...]"; exit 2; }
LIVE=/opt/nox-web; NEW=/opt/nox-web.new; TMP=/opt/.nox-web-dl
LOCK=/tmp/nox-web-deploy.lock
mkdir "$LOCK" 2>/dev/null || { echo "BUSY: $LOCK"; exit 3; }
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

[ "$(cat $LIVE/.deploy_sha 2>/dev/null)" = "$SHA" ] && { echo "UP_TO_DATE $SHA"; exit 0; }

# места: нужно ~ (архив + распаковка) * 1.3, считаем запас 1.5 ГБ
FREE=$(df -Pk /opt | awk 'NR==2{print $4}')
[ "$FREE" -lt 1500000 ] && { echo "NO_SPACE free_kb=$FREE"; exit 4; }

# только свои временные каталоги прошлых неудачных попыток
rm -rf "$NEW" "$TMP"; mkdir -p "$TMP" || exit 5
i=0; : > "$TMP/pkg"
for u in "$@"; do
  i=$((i+1))
  curl -fsSL --retry 3 --retry-delay 5 -m 240 "$u" >> "$TMP/pkg" || { echo "DOWNLOAD_FAILED part=$i"; rm -rf "$TMP"; exit 6; }
done
GOT=$(sha256sum "$TMP/pkg" | cut -d' ' -f1)
[ "$GOT" = "$SHA" ] || { echo "SHA_MISMATCH got=$GOT"; rm -rf "$TMP"; exit 7; }

mkdir -p "$NEW"
if head -c4 "$TMP/pkg" | od -An -tx1 | grep -q "28 b5 2f fd"; then
  command -v zstd >/dev/null || { echo "NO_ZSTD"; rm -rf "$TMP" "$NEW"; exit 8; }
  zstd -dc "$TMP/pkg" | tar -x -C "$NEW" --no-same-owner
else
  tar -xJf "$TMP/pkg" -C "$NEW" --no-same-owner
fi || { echo "UNPACK_FAILED"; rm -rf "$TMP" "$NEW"; exit 9; }
rm -rf "$TMP"
[ -f "$NEW/index.html" ] || { echo "NO_INDEX_HTML (не веб-сборка)"; rm -rf "$NEW"; exit 10; }
echo "$SHA" > "$NEW/.deploy_sha"; chmod -R a+rX "$NEW"

HAD=0; [ -e "$LIVE" ] && HAD=1
if [ $HAD -eq 1 ]; then
  if mv --exchange "$NEW" "$LIVE" 2>/dev/null; then     # атомарный обмен (coreutils>=9.5)
    mv "$NEW" "$LIVE.prev.$(date +%Y%m%d%H%M%S)"
  else
    mv "$LIVE" "$LIVE.prev.$(date +%Y%m%d%H%M%S)" && mv "$NEW" "$LIVE"
  fi
else
  mv "$NEW" "$LIVE"
fi || { echo "SWITCH_FAILED"; exit 11; }

# bridge монтирует /web только при старте, если каталог существовал; перезапуск нужен, лишь если /web ещё не отдаётся
sleep 1
CODE=$(curl -s -o /dev/null -m5 -w '%{http_code}' http://127.0.0.1:8091/web/ || echo 000)
if [ "$CODE" != "200" ]; then
  echo "web code=$CODE -> restart nox-bridge"
  supervisorctl restart nox-bridge >/dev/null 2>&1; sleep 8
  CODE=$(curl -s -o /dev/null -m5 -w '%{http_code}' http://127.0.0.1:8091/web/ || echo 000)
fi
echo "DEPLOYED sha=$SHA web=$CODE"; curl -s -m5 http://127.0.0.1:8091/api/health | cut -c1-200; echo
df -h / | tail -1
