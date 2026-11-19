# NOX_CONTROL_V1 — control-plane protocol

State: GitHub files created, agents not deployed. Poll interval: 180 seconds.

## Components
- `NOX_MASTER.json`: shared **manifest**, currently no jobs.
- `nox_agent.py`: Python 3.9+ polling reader, read-only actions.
- No automatic remote terminal. Never interpret task fields as shell.
- Repository currently PUBLIC: task content and reports must contain no credentials, secrets or personal data.

## Task record (add to tasks array)
```json
{
  "id": "example-health-20261109-01",
  "target": "runpod-a40",
  "action": "health",
  "expires_at": "2026-11-10T00:00:00Z"
}
```
Allowed target strings: `windows`, `runpod-a40`, `runpod-a5000`, `contabo`, `all`.
Actions: `health`, `gpu_status`, `nox_status`.
No arbitrary scripts, downloads, process termination, deployment or model changes in v1.

## Install and start (Linux Pod, one terminal each)
```bash
mkdir -p "$HOME/nox-control"
curl -fL --retry 3 -o "$HOME/nox-control/nox_agent.py" "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/nox_agent.py"
python3 "$HOME/nox-control/nox_agent.py" --target runpod-a40
```
Use `runpod-a5000` for that machine. This foreground test stops when terminal exits. Once verified, configure a supervised service with persistent disk/state and a host-specific name. Do not start multiple agents with the same identity/state directory.

## Install and start (Windows PowerShell)
```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\nox-control" | Out-Null
Invoke-WebRequest "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/nox_agent.py" -OutFile "$env:USERPROFILE\nox-control\nox_agent.py"
py -3 "$env:USERPROFILE\nox-control\nox_agent.py" --target windows
```
Requires Python 3.9+. This is not a Windows service; initial run is a foreground test.

## Results and security
- Result is printed as `NOX_RESULT` and saved locally in `~/.nox-control/completed.json`.
- No remote write-back endpoint has been configured. ChatGPT does not yet receive results automatically.
- To support mutating commands, use private signed authorizations, scoped credentials, confirmation, atomic job claims and append-only audit results.
- STOP/Safe70 for training remain independently enforced by the GPU host, and must never be overridden by tasks.
- GitHub raw CDN caching and network latency mean polling is *approximately* every 180 seconds, not a realtime SLA.
- A single JSON file is suitable for a low-frequency control manifest, not a high-throughput or exactly-once queue. Host-specific state prevents repeats locally; distributed exactly-once guarantees are not provided.
