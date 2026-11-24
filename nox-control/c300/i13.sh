grep -B14 "AttributeError: xformers" /workspace/nox/svc/logs/invoke.log | tail -16 | cut -c1-230
