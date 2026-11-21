#!/bin/bash
# T2.1: GLM-5.3 UD-Q4_K_XL -> /dev/shm (шарды, что влезают) + остаток на диск; фон, докачка, идемпотентно.
D=/root/nox/glm53; mkdir -p $D /root/nox/glm53_disk /root/nox/logs
exec 9>/root/nox/logs/glm_dl.lock; flock -n 9 || { echo "already running"; tail -3 /root/nox/logs/glm_dl.log; exit 0; }
umount_try=$(mount -o remount,size=480G /dev/shm 2>&1) ; echo "remount: ${umount_try:-ok}"; df -h /dev/shm | tail -1
cat > /root/nox/scripts_glm_dl_worker.sh <<'W'
#!/bin/bash
B=https://huggingface.co/unsloth/GLM-5.3-GGUF/resolve/main/UD-Q4_K_XL
get(){ i=$1; n=$(printf "GLM-5.3-UD-Q4_K_XL-%05d-of-00011.gguf" $i)
  sz=$(curl -fsSIL "$B/$n" | tr -d '\r' | awk 'tolower($1)=="content-length:"{s=$2} END{print s}')
  free=$(df -B1 --output=avail /dev/shm | tail -1)
  if [ "$free" -gt $((sz+3*1024**3)) ]; then T=/dev/shm/nox_glm; else T=/root/nox/glm53_disk; fi
  mkdir -p $T; ln -sf $T/$n /root/nox/glm53/$n
  [ -f $T/$n ] && [ "$(stat -c %s $T/$n)" = "$sz" ] && { echo "$n ok(skip) $T"; return; }
  for try in 1 2 3 4 5 6; do curl -fL -C - --retry 5 -o $T/$n "$B/$n" && break; sleep 5; done
  echo "$n $(stat -c %s $T/$n)/$sz -> $T"; }
export -f get; export B
# последовательное решение куда класть (чтобы не гонять df), параллель 4
for i in 1 2 3 4 5 6 7 8 9 10 11; do echo $i; done | xargs -P4 -I{} bash -c 'get {}'
echo DONE $(date)
W
chmod +x /root/nox/scripts_glm_dl_worker.sh
nohup setsid bash -c 'exec 9>&-; /root/nox/scripts_glm_dl_worker.sh' > /root/nox/logs/glm_dl.log 2>&1 < /dev/null &
sleep 20; cat /root/nox/logs/glm_dl.log; ls -la /dev/shm/nox_glm /root/nox/glm53_disk 2>/dev/null | head; df -h /dev/shm | tail -1
