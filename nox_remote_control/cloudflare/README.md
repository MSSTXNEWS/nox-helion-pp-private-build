# NOX HELION — Cloudflare Access control gateway (phase 1)

Two existing hosts: **RunPod A100** `5f3j8hwyicc0bp` and **Vast.ai A4000** `60254538`.

This PR provides a standalone **localhost-bound read-only API** (port 18796), preserving existing NOX36, S03, checkpoints, scripts, GPU training and the established GitHub observers. It does NOT start `cloudflared` and does NOT publish an endpoint automatically.

## Endpoint contract

`GET /v1/health`, `/v1/gpu`, `/v1/processes`, `/v1/disk`, `/v1/checkpoints`. No shell command, token echo, model download, process termination, POST, file mutation or arbitrary path selection. Limited response sizes, concurrency and timeouts. GPU values come from the real `nvidia-smi`; unmeasured values return HOLD.

The reported checkpoint count is **not evidence of valid weight tensors or completed optimizer steps**. The API intentionally does not inspect `/workspace` during requests because its network-mounted filesystem has previously hung.

## Step 1 — install isolated API, locally (after reviewing pinned source)

RunPod web terminal:

```bash
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/6af7061f1861781502856048f28a822b5cb96769/nox_remote_control/cloudflare/install_local_api.sh -o /tmp/nox-cf-install.sh && bash /tmp/nox-cf-install.sh runpod-5f3j8hwyicc0bp
```

Vast.ai web terminal:

```bash
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/6af7061f1861781502856048f28a822b5cb96769/nox_remote_control/cloudflare/install_local_api.sh -o /tmp/nox-cf-install.sh && bash /tmp/nox-cf-install.sh vast-60254538
```

The installer pins the Python Git blob checksum and refuses to replace a different existing API. Confirm `NOX_CONTROL_API_HEALTH_OK` and `CLOUDFLARE_NOT_CONFIGURED`. Nothing is exposed to the internet yet.

## Step 2 — configure Cloudflare in the user's account

Prerequisites: Cloudflare account and a domain with Cloudflare DNS. Cloudflare Docs: https://developers.cloudflare.com/tunnel/get-started/

1. In Cloudflare Zero Trust/Access, create **two self-hosted Access applications** with intended hostnames (e.g. `nox-runpod.<your-domain>` and `nox-vast.<your-domain>`). Restrict Allow to the owner's email identity; default deny all other identities. For a future machine client, add a separate Service Auth policy and dedicated service token for each hostname. **Do not create a Bypass policy.**
2. In Cloudflare dashboard go to **Networking > Tunnels**, create one remotely-managed tunnel per node. Set its published application service to `http://localhost:18796`. Do NOT use `http://0.0.0.0:18796`, route SSH/Jupyter, or map any trainer port.
3. In the server terminal, install `cloudflared` using the official Cloudflare command shown for that tunnel. The tunnel run token is a secret: enter it only on the respective host, never in GitHub, screenshots, or chat.
4. Verify each tunnel is **Healthy**, and public hostname returns Access login/403 before authentication, not raw NOX data. Then check authenticated `GET /v1/health`.

Official Access service tokens docs: https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/

## Future phase — controlled operations

No arbitrary `root` shell through cloud access. Commands like start/trainer/stop/transfer require a **second**, separately audited dispatcher, an operation allowlist, exact target process ownership, per-request idempotency, time-limited scoped authorization, explicit confirmation for impactful actions and verified checkpoints. No automation should start old jobs or stop unidentified processes.

## Acceptance boundary

GitHub source review is not live deployment. Cloudflare setup requires user account access; the connected RunPod tool currently has Pod lifecycle but no arbitrary terminal execution. Never claim access or training success without endpoint and checkpoint receipts.
