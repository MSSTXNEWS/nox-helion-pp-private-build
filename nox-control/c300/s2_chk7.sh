#!/bin/bash
cat /workspace/nox/svc/logs/s2_once.log | cut -c1-300; ls -la /workspace/nox/web/site/data/ | cut -c1-120; pgrep -fa s2_feeds | cut -c1-100
curl -s -m 20 'https://archive.org/advancedsearch.php?q=collection%3Anetlabels+AND+mediatype%3Aaudio&fl%5B%5D=identifier&rows=3&output=json' | head -c 300
