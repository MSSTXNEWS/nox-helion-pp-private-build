echo "C300: srv_k105"
cd /workspace/nox; grep -n "stop_flag\|STOP" imgsvc/image_service.py | cut -c1-200
ls -la STOP; tail -n 3 ops/dpo/run5.log 2>/dev/null
