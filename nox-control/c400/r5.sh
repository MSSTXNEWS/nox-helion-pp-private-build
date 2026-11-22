#!/bin/bash
echo BIG:; find /root /mnt /data -xdev -type f -size +20M \( -iname '*.jsonl' -o -iname '*.json' -o -iname '*.db' -o -iname '*.sqlite*' -o -iname '*.zip' -o -iname '*.tar*' -o -iname '*.csv' \) -not -path '*/backups/*' -not -path '*/proc/*' -printf '%s %TY-%Tm-%Td %p\n' 2>/dev/null | sort -rn | head -14 | cut -c1-140
echo FNS:; grep -nE "^def |^class |^    def " /root/nox/scripts/lib/nox_s03.py | grep -iE "import|restore|ingest|load|upsert|add_fact|dedup" | head -12
grep -rlE "mem_import_reports" /root/nox/scripts /root/nox/repo/nox-control 2>/dev/null | head -6
