#!/bin/bash
# Чинит склейку строк в authorized_keys (нет \n в конце) и проверяет ограниченный ключ S1
python3 - <<'P'
import os
p=os.path.expanduser('~/.ssh/authorized_keys'); t=open(p).read()
t=t.replace('nox-update-buttonrestrict,','nox-update-button\nrestrict,')
t=t.rstrip('\n')+'\n'
open(p,'w').write(t)
P
chmod 600 ~/.ssh/authorized_keys
grep -n "s1pull" ~/.ssh/authorized_keys | cut -c1-90; grep -c "nox-update-button$" ~/.ssh/authorized_keys; wc -l ~/.ssh/authorized_keys
