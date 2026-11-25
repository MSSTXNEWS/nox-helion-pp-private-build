echo "C300: k8_probe_4"
tail -n 25 /workspace/nox/agent/out/web_server.log | cut -c1-250
ls -la /workspace/nox/web/pkg/server/ | grep -i "web_server\|run_web" | head
ps aux | grep -c "web_server"
echo "K8 probe4 done"
