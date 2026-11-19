#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo '=== NOX V38: READ-ONLY GPU/CORE CONTROLLER ==='
PYTHONPATH=. python3 -m nox_runpod.teacher_mesh.v38.noxctl status
echo '=== NOX V38: CACHE-CANDIDATE PREVIEW, NO DELETE ==='
PYTHONPATH=. python3 -m nox_runpod.teacher_mesh.v38.noxctl cleanup-plan
