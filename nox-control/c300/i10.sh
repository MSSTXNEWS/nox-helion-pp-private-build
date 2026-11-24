V=/workspace/nox/invoke/lib/python3.10/site-packages
grep -rl "from typing import.*\bSelf\b" $V/invokeai $V/diffusers $V/compel $V/dynamicprompts 2>/dev/null | head
grep "File" /workspace/nox/svc/logs/invoke.log | tail -3 | cut -c1-200
