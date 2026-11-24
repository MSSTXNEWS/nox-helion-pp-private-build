F=/workspace/nox/invoke/lib/python3.10/site-packages/diffusers/quantizers/torchao/torchao_quantizer.py
sed -i '20i import logging as _lg\nlogger = _lg.getLogger(__name__)' $F
nohup setsid bash /workspace/nox/svc/start_extra.sh >/dev/null 2>&1 &
sleep 80
grep -v "^\s*File\|^\s\s" /workspace/nox/svc/logs/invoke.log | tail -6 | cut -c1-240
curl -s -m5 -w "\napi %{http_code}\n" localhost:9090/api/v1/app/version
curl -s -m5 localhost:9090/ | grep -o '<script[^>]*>\|<link[^>]*>\|<base[^>]*>' | head -6
