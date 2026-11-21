#!/usr/bin/env bash
# Local SearXNG on 127.0.0.1:8888 via Docker. Dry-run by default; --apply to execute.
# Never exposes the port outside localhost. Secret is generated locally, not printed.
set -euo pipefail
APPLY=0; [ "${1:-}" = "--apply" ] && APPLY=1
DIR="${SEARXNG_DIR:-/root/nox/searxng}"
run() { echo "+ $*"; [ "$APPLY" = 1 ] && "$@"; return 0; }
echo "mode: $([ "$APPLY" = 1 ] && echo APPLY || echo DRY-RUN) dir=$DIR port=127.0.0.1:8888"
if ! command -v docker >/dev/null 2>&1; then
  echo '{"ok":false,"blocked":"docker not installed","need":"owner/server admin: install docker (apt install docker.io)"}'
  [ "$APPLY" = 1 ] && exit 2
fi
run mkdir -p "$DIR"
if [ "$APPLY" = 1 ]; then
  SECRET="$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  cat > "$DIR/settings.yml" <<YML
use_default_settings: true
server:
  secret_key: "$SECRET"
  limiter: false
search:
  formats: [html, json]
YML
  chmod 600 "$DIR/settings.yml"
else
  echo "+ write $DIR/settings.yml (random secret_key, formats html+json, chmod 600)"
fi
run docker rm -f nox-searxng || true
run docker run -d --name nox-searxng --restart unless-stopped -p 127.0.0.1:8888:8080 \
  -v "$DIR/settings.yml:/etc/searxng/settings.yml:ro" searxng/searxng:latest
echo "check: curl -s 'http://127.0.0.1:8888/search?q=test&format=json' | head -c 200"
