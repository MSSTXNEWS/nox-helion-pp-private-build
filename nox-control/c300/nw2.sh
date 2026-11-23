#!/usr/bin/env bash
# Read-only, bounded S1 diagnostic. Never print argv, environment or startup-file contents.
set -euo pipefail
export LC_ALL=C
printf 'NOX_DIAG_SAFE_V1\n'
ps -eo pid=,rss=,comm= --sort=-rss | awk '
NR <= 12 && $1 ~ /^[0-9]+$/ && $2 ~ /^[0-9]+$/ {
    exe = $3
    if (exe !~ /^[A-Za-z0-9_.-]+$/ || length(exe) > 48) exe = "redacted"
    printf "pid=%s rss_kib=%s service=%s\n", $1, $2, exe
}'
if command -v ss >/dev/null 2>&1; then
  ss -ltnH | awk '{
      n=split($4, parts, ":"); port=parts[n]
      if (port ~ /^[0-9]+$/ && !seen[port]++ && count++ < 20)
          printf "listen_tcp_port=%s\n", port
  }'
else
  printf 'tcp_listen_status=UNAVAILABLE\n'
fi
for dir in /workspace/nox /root/nox; do
  if [ -d "$dir" ]; then
    printf 'directory_status=%s:present\n' "$dir"
  else
    printf 'directory_status=%s:absent\n' "$dir"
  fi
done
# The existence of startup tooling is useful; its source/arguments are not.
if [ -f /root/onstart.sh ]; then
  printf 'startup_script=present\n'
else
  printf 'startup_script=absent\n'
fi
