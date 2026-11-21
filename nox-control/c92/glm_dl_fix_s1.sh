#!/bin/bash
# shm=371G (remount запрещён): шарды 1-9 -> /dev/shm, 10-11 -> диск. Докачка с места остановки.
pkill -f scripts_glm_dl_worker; pkill xargs; pkill curl; sleep 2
D=/dev/shm/nox_glm; X=/root/nox/glm53_disk; mkdir -p $D $X
for i in 10 11; do n=$(printf "GLM-5.3-UD-Q4_K_XL-%05d-of-00011.gguf" $i); [ -f $D/$n ] && mv -n $D/$n $X/$n; done
cat > /root/nox/scripts_glm_dl_worker.sh <<'W'
#!/bin/bash
B=https://huggingface.co/unsloth/GLM-5.3-GGUF/resolve/main/UD-Q4_K_XL
get(){ i=$1; n=$(printf "GLM-5.3-UD-Q4_K_XL-%05d-of-00011.gguf" $i)
  sz=$(curl -fsSIL "$B/$n" | tr -d '\r' | awk 'tolower($1)=="content-length:"{s=$2} END{print s}')
  if [ $i -le 9 ]; then T=/dev/shm/nox_glm; else T=/root/nox/glm53_disk; fi
  ln -sf $T/$n /root/nox/glm53/$n
  [ -f $T/$n ] && [ "$(stat -c %s $T/$n)" = "$sz" ] && { echo "$n ok(skip) $T"; return; }
  for try in 1 2 3 4 5 6; do curl -fsSL -C - --retry 5 -o $T/$n "$B/$n" && break; sleep 5; done
  echo "$n $(stat -c %s $T/$n)/$sz -> $T"; }
export -f get; export B
for i in 1 2 3 4 5 6 7 8 9 10 11; do echo $i; done | xargs -P6 -I{} bash -c 'get {}'
echo DONE $(date)
W
nohup setsid bash -c 'exec 9>&-; /root/nox/scripts_glm_dl_worker.sh' > /root/nox/logs/glm_dl.log 2>&1 < /dev/null &
sleep 15; du -sh $D $X; df -h /dev/shm | tail -1; pgrep -c curl
