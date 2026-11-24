F=/workspace/nox/invoke/lib/python3.10/site-packages/invokeai/backend/util/hotfixes.py
sed -i 's/^\(\s*\)_xformers_memory_efficient_attention = xformers.ops.memory_efficient_attention/\1try:\n\1    _xformers_memory_efficient_attention = xformers.ops.memory_efficient_attention\n\1except Exception:\n\1    _xformers_memory_efficient_attention = None/' $F
sed -n 805,816p $F
for i in 1 2; do
  pkill -f invokeai-web; sleep 1
  nohup setsid bash /workspace/nox/svc/start_extra.sh >/dev/null 2>&1 &
  sleep 70
  curl -s -m5 -o /dev/null -w "api %{http_code}\n" localhost:9090/api/v1/app/version | grep -q "api 200" && break
  grep -v "^\s*File\|^\s\s\|^W\|^I0\|^E0\|^2026\|^To enable" /workspace/nox/svc/logs/invoke.log | tail -3 | cut -c1-240
done
curl -s -m5 -w "\napi %{http_code}\n" localhost:9090/api/v1/app/version
curl -s -m5 localhost:9090/ | grep -o '<script[^>]*>\|<link[^>]*>\|<base[^>]*>' | head -6
