echo "C300: srv_k30"
cd /workspace/nox/distill_v2/code
grep -n "yield\|chat_hold\|уступ\|probe\|def cmd_\|add_parser\|subparsers\|im_id\s*=\|gates_on\s*=\|gate_persona_error\s*=\|NOX_PERSONA\s*=" distill_v2.py | cut -c1-210 | head -70
