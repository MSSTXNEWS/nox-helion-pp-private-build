#!/bin/bash
G=/workspace/nox/advisors/gateway.py
wc -l $G; grep -n -E "^def |^class |^    def |MOCKQA|P3_PRIVATE|PRIVATE_TOPICS|prio|counter|stats|json.dump" $G | cut -c1-170 | head -90
pgrep -af advisors/gateway | head -3; ls /workspace/nox/advisors | head -30
