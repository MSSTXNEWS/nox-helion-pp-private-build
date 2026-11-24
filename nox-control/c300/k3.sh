#!/bin/bash
cd /workspace/nox/web; head -c 2500 DEPLOY.md; echo; echo =====; head -c 2500 REPORT.md; echo; ls server deploy | tr '\n' ' '
