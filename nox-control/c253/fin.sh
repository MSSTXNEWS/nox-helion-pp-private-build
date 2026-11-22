#!/bin/bash
pkill -f glm_watch.sh; sleep 1
cat > /root/nox/receipts/V7-01.json <<'J'
{"id":"V7-01","ok":true,"stage":"recon+baseline","baseline":{"cmd":"taskset -c 0-17 nice -n19 ik_llama llama-server -ngl 22 -ot exps=CPU -c 16384 -np 1 -fa on -amb 512 -t22 -tb26 -b2048 -ub512 GGML_CUDA_NO_PINNED=1","short":{"tg":1.68,"pp":3.6,"ttft_ms":4971},"long1450":{"tg":1.24,"pp":17.8,"ttft_ms":81511}},"cgroup_quota_vcpu":26.88,"vcpu_visible":112,"sockets":2,"phys_cores":56,"numa":2,"numactl_installed":false,"blocker":"04:16 кто-то удалил шарды GLM-5.3 из /dev/shm/nox_glm и симлинки /root/nox/glm53 (пусто), качает GLM-5.3-Flash в /dev/shm/glm53f; рычаги не гонялись"}
J
ps -eo pid,etime,args | grep -E 'llama-server|glm_watch|exp_driver' | grep -v grep | cut -c1-120
