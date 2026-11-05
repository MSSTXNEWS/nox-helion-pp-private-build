# BLOCK 1 — live functions and build gates — 2026-11-03

## Live functions
| Function | Now |
|----------|-----|
| Chat with model | local input, no Ollama |
| One history / SQLite | missing |
| RAG | missing |
| Catalog 24+ and pull | missing |
| GPU training | no GPU |
| STOP/PAUSE training | missing |
| events.v3 live | stub |
| CPU/GPU sensors | local, not host |
| Mail, calls, voice, PC Control | HOLD |
| 5 progress bars | missing |
| Native ACK | not run |

## Build still needs
1. Seal PATCH-A and PATCH-B (CAS + I0)
2. Weights 7B + embedding in runtime
3. Windows runner
4. Current private_build.ps1 on PR162
5. Shell EXE
6. Filled payload.sha256.json
7. NSIS preflight, verify, setup

## This host
Seal, Windows runner, EXE, filled payload, E07 cannot be completed here.
