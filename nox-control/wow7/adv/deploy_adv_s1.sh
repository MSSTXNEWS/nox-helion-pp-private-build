#!/usr/bin/env bash
# ADV-01: установка внешних советников NOX на S1. Использование: deploy_adv_s1.sh [--dry-run] [--src DIR] [--root /root/nox] [--no-system] [--port 8095]
# Ключи НЕ в скрипте и не в репо: файл $ROOT/secrets/advisors.env (chmod 600), его заполняет Создатель (SETUP.md). Существующий env не перезаписывается.
# Квитанция: $ROOT/receipts/ADV-01.json
set -euo pipefail
DRY=0; NOSYS=0; PORT=8095; ROOT=/root/nox; SRC="$(cd "$(dirname "$0")" && pwd)"
while [ $# -gt 0 ]; do case "$1" in --dry-run) DRY=1;; --no-system) NOSYS=1;; --src) SRC="$2"; shift;; --root) ROOT="$2"; shift;; --port) PORT="$2"; shift;; *) echo "unknown $1" >&2; exit 2;; esac; shift; done
DEST=$ROOT/src/adv; ENVF=$ROOT/secrets/advisors.env; REC=$ROOT/receipts/ADV-01.json
WORLD="$SRC/../WORLD"; COMMON="$SRC/../COMMON"; [ -f "$SRC/advisor_pool.py" ] && WORLD="$SRC"; [ -d "$SRC/common" ] && COMMON="$SRC/common"
run() { if [ "$DRY" = 1 ]; then echo "[dry-run] $*"; else eval "$*"; fi; }
for f in advisor_hub.py health_check.py handoff.py advisors_live.json test_adv.py; do [ -f "$SRC/$f" ] || { echo "нет $SRC/$f" >&2; exit 1; }; done
[ -f "$WORLD/advisor_pool.py" ] || { echo "нет advisor_pool.py ($WORLD)" >&2; exit 1; }
for f in datafence.py statefile.py; do [ -f "$COMMON/$f" ] || { echo "нет $COMMON/$f" >&2; exit 1; }; done
run "mkdir -p $DEST/common $ROOT/state $ROOT/logs $ROOT/receipts $ROOT/scripts $ROOT/secrets && chmod 700 $ROOT/secrets"
run "cp $SRC/advisor_hub.py $SRC/health_check.py $SRC/handoff.py $SRC/advisors_live.json $SRC/test_adv.py $WORLD/advisor_pool.py $DEST/"
run "cp $COMMON/*.py $DEST/common/"
if [ -f "$ENVF" ]; then echo "env уже есть: $ENVF (не трогаю)"; else
  TPL='# ключи бесплатных советников NOX (SETUP.md). Только KEY=значение, без кавычек. Файл chmod 600, в git не класть.
GROQ_API_KEY=
CEREBRAS_API_KEY=
OPENROUTER_API_KEY=
GEMINI_API_KEY=
MISTRAL_API_KEY=
NVIDIA_API_KEY=
CLOUDFLARE_API_TOKEN=
CF_ACCOUNT_ID=
# Подтверждаю: к этим ключам НЕ привязаны карта/оплата (через запятую из: groq,cerebras,google,mistral,nvidia,cloudflare)
NOX_ADV_FREE_CONFIRMED=
# необязательно
NOX_ADV_TOKEN=
NOX_FAST_URL=http://127.0.0.1:8083/v1
NOX_SEARXNG_URL=http://127.0.0.1:8888'
  if [ "$DRY" = 1 ]; then echo "[dry-run] создам $ENVF (chmod 600) с шаблоном ключей"; else printf '%s\n' "$TPL" > "$ENVF"; chmod 600 "$ENVF"; fi; fi
RUNSH="#!/usr/bin/env bash
set -a; . $ENVF; set +a
export NOX_ADVPOOL=$ROOT/state/advisor_pool.json NOX_ADV_LOG=$ROOT/logs/advisors.jsonl NOX_ADV_PORT=$PORT
cd $DEST && exec python3 advisor_hub.py serve --port $PORT >>$ROOT/logs/advisor_hub.out 2>&1"
if [ "$DRY" = 1 ]; then echo "[dry-run] $ROOT/scripts/run_advisors.sh <<"; echo "$RUNSH"; else printf '%s\n' "$RUNSH" > "$ROOT/scripts/run_advisors.sh"; chmod 755 "$ROOT/scripts/run_advisors.sh"; fi
if [ "$NOSYS" = 0 ]; then
  UNIT="[Unit]
Description=NOX external advisors hub
After=network-online.target
[Service]
ExecStart=$ROOT/scripts/run_advisors.sh
Restart=on-failure
RestartSec=5
[Install]
WantedBy=multi-user.target"
  CRON="17 6 * * * root set -a; . $ENVF; set +a; cd $DEST && python3 health_check.py --stamp >>$ROOT/logs/advisor_health.log 2>&1"
  if [ "$DRY" = 1 ]; then echo "[dry-run] /etc/systemd/system/nox-advisors.service (если есть systemctl) <<"; echo "$UNIT"; echo "[dry-run] /etc/cron.d/nox-advisors <<"; echo "$CRON"
  else
    if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then printf '%s\n' "$UNIT" > /etc/systemd/system/nox-advisors.service; systemctl daemon-reload; systemctl enable --now nox-advisors || true
    else echo "нет systemd: запуск вручную: nohup $ROOT/scripts/run_advisors.sh &"; fi
    printf '%s\n' "$CRON" > /etc/cron.d/nox-advisors
  fi
fi
if [ "$DRY" = 1 ]; then echo "[dry-run] unittest (фейковые провайдеры), health_check, квитанция $REC"; echo "[dry-run] шлюз: проксировать /v1/advisors/* на http://127.0.0.1:$PORT (gateway.py - отдельной карточкой)"; exit 0; fi
TESTS=$(cd "$DEST" && python3 -W ignore -m unittest test_adv 2>&1 | tail -3 | tr '\n' ' ' | sed 's/"//g')
TOK=0; case "$TESTS" in *OK*) TOK=1;; esac
set -a; . "$ENVF"; set +a
KEYS=""; for k in GROQ_API_KEY CEREBRAS_API_KEY OPENROUTER_API_KEY GEMINI_API_KEY MISTRAL_API_KEY NVIDIA_API_KEY CLOUDFLARE_API_TOKEN; do
  if [ -n "${!k:-}" ]; then KEYS="$KEYS\"$k\":true,"; else KEYS="$KEYS\"$k\":false,"; fi; done
HC=$(cd "$DEST" && NOX_ADV_LOG=/dev/null python3 health_check.py --receipt "$ROOT/receipts/ADV-health.json" --stamp 2>&1 | tail -1 | sed 's/"//g' || true)
printf '{"id":"ADV-01","ts":%s,"dest":"%s","env_file":"%s","keys_present":{%s},"tests_ok":%s,"tests":"%s","health":"%s","port":%s,"gateway_todo":"proxy /v1/advisors/* -> 127.0.0.1:%s","ok":%s}\n' \
  "$(date +%s)" "$DEST" "$ENVF" "${KEYS%,}" "$([ $TOK = 1 ] && echo true || echo false)" "$TESTS" "$HC" "$PORT" "$PORT" "$([ $TOK = 1 ] && echo true || echo false)" > "$REC"
cat "$REC"
