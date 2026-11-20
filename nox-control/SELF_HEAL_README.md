# NOX Self-Heal guard — staged source, NOT deployed

The only scheduler stays the existing OneHost dispatcher. The guard observes locally approved systemd units and can restart **only** units individually enabled by a trusted local administrator in /etc/nox/repair-policy.json. GitHub manifests and model output cannot activate restart. Default policy is disabled. Do not enable restart until the exact OneHost unit and a working health endpoint have been verified.

## Setup on the original Linux host only

1. Install the reviewed repo version of `nox_self_heal.py` to `/opt/nox/nox-control/`, and example policy to `/etc/nox/repair-policy.json`. Ensure /var/lib/nox exists. Review exact current unit names and endpoint; the sample is **illustrative**, not a claim about the running host.
2. Check `python3 /opt/nox/nox-control/nox_self_heal.py --policy /etc/nox/repair-policy.json --state /var/lib/nox/repair-state.json --once --dry-run`.
3. Install `systemd/nox-self-heal.service` to `/etc/systemd/system/nox-self-heal.service`; run `systemctl daemon-reload && systemctl enable --now nox-self-heal.service` only after live acceptance.
4. Check `systemctl status nox-self-heal.service`, `journalctl -u nox-self-heal.service -n 100`, and read the local repair-state.json.
5. To enable bounded restarts change the local policy `enabled=true` and the specific reviewed unit's `restart_enabled=true`; maintain STOP, GPU thermal watchdog and checkpoint protection outside this guard.

For continuous training, use the **existing** OneHost queue and trainer. Admission requires an actual healthy checkpoint and restart/resume test, available GPU/VRAM/disk, live thermal sensors, verified teacher/student provenance, live CPU/cgroup limits, and foreground chat priority. Do not restart healthy training on a schedule. Every training window must commit checkpoint, optimizer state, lineage and independently verify readback; merge weights only after compatible-base checks, evaluation and rollback snapshot. Distillation, LoRA and merging are distinct operations, not interchangeable success states.

NOX can inspect dispatcher evidence and propose optimizations, but may not disable STOP, bypass SAFE70, elevate capabilities or edit local repair policy via model-generated commands. A second independent guard is intentionally *not* an AI agent and does not touch S03 or weights.

## Open live gates
- Host deployment: **NOT DONE**.
- Exact systemd unit name and auth health route: **UNVERIFIED**.
- Continuous process monitoring: **NOT RUNNING until installed**.
- Restart, training, self-tuning throughput benchmark and S03/weights regression: **UNTESTED on physical server**.
