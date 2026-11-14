# NOX BRAIN MAX V5 · GPU thermal safety policy
instructions_version: 0.0.6 · 2026-11-06

Approved user setting: GPU temperature limit **65 °C** (measured with `nvidia-smi --id=0 --query-gpu=temperature.gpu --format=csv,noheader,nounits`).

- Temperature <65 °C: continue CUDA QLoRA without fixed cooling delay.
- Temperature >=65 °C: pause training **at the next safe training-step boundary** for at least **180 seconds**.
- Resume only when GPU core temperature <=60 °C; otherwise repeat 180-second cooling interval.
- If temperature telemetry fails, stop training and report THERMAL_HOLD; no blind continuation.
- After 12 consecutive cooldown cycles without reaching <=60 °C, stop with THERMAL_HOLD.
- Monitor temperature before and after training steps and around holdout evaluations; no claim of instantaneous mid-kernel interruption.
- The thermal policy is not a substitute for GPU hardware thermal control, CPU/hotspot/VRAM sensors, fans, power supply or airflow health.

Canonical quotas unchanged: intelligence 70 GB / memory 70 GB / skills 70 GB, free reserve 60 GB, 270 GB total project allocation.
No automatic deletion of Downloads. No duplicate model pulls. No unverifiable data labeled as trained.
WOW MOTION V7: existing installed NOX.exe may be opened by controller, but local V7 installation and UI telemetry hookup remain UNVERIFIED; real learning progress is displayed in PowerShell and JSON.

Local V5 deliverable: `NOX_BRAIN_MAX_V5_65C.zip` with `NOX_BRAIN_MASTER_V5.ps1`, `nox_train_with_status.py`, `README_RU.txt`. ZIP SHA-256: `625f98353b265dc03e9838438d9b92af26a7ca9c0864300d83910a92b8061a1a`.

Local checks completed: Python syntax (py_compile), no-pause under threshold, 65°C pause 180s, cooldown until 60°C, sensor outage to HOLD. **No real Windows/GPU thermal run or trained LoRA output verified.**
