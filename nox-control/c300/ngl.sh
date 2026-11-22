#!/bin/bash
# A/B: -ngl 99 (все слои внимания на GPU), при OOM вернуть 24
cp /root/nox/start_glm.sh /root/nox/start_glm.sh.ngl24
sed -i 's/-ngl 24/-ngl 99/' /root/nox/start_glm.sh
cat > /root/nox/flash_ab2.sh <<'S'
#!/bin/bash
bash /root/nox/flash_ab.sh
if ! grep -q "^pp" /root/nox/logs/flash_ab.log; then
  echo "ngl99 FAILED -> back to 24" >> /root/nox/logs/flash_ab.log; grep -iE "out of memory|error" /root/nox/logs/glm_8081.log | head -3 >> /root/nox/logs/flash_ab.log
  cp /root/nox/start_glm.sh.ngl24 /root/nox/start_glm.sh; cp /root/nox/logs/flash_ab.log /tmp/ab99.log; bash /root/nox/flash_ab.sh; cat /tmp/ab99.log >> /root/nox/logs/flash_ab.log
fi
S
nohup setsid bash /root/nox/flash_ab2.sh >/dev/null 2>&1 < /dev/null &
echo started ngl99
