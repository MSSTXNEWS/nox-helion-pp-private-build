ss -ltnp 2>/dev/null | awk 'NR>1{print $4, $6}' | sed 's/users:(("//; s/".*//' | sort -t: -k2 -n | tr '\n' ';' | cut -c1-1800
