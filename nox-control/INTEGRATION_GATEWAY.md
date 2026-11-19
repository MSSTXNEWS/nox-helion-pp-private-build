# NOX integration gateway · server deployment

Source: `nox-control/nox_integration_gateway.py`. Status-only, no mutations and no arbitrary remote commands.
This is an integration **probe**, not a completed provider authorization.

## Secure configuration (on the actual NOX host)

Provide only the credentials you choose to authorize, as systemd environment/credential files
restricted to the dedicated `nox` account. **Never commit tokens or rclone.conf to GitHub.**

Environment names:
- `NOX_DRIVE_REMOTE=noxdrive:` — existing rclone remote name. OAuth is initialized on a trusted machine and imported securely to the host. Grant only the dedicated NOX Drive folder via a limited service identity where possible. `rclone lsjson` is read-only.
- `NOX_GITHUB_TOKEN` — fine-grained repository-scoped token for `MSSTXNEWS/nox-helion-pp-private-build`; set `NOX_GITHUB_REPOSITORY` if repository differs.
- `NOX_GITLAB_TOKEN` and `NOX_GITLAB_PROJECT=group/project` — project-scoped token, not a personal administrator token.
- `NOX_NOTION_TOKEN` — dedicated integration token with explicitly shared NOX pages, not unrestricted workspace access.
- `NOX_VAST_API_KEY` and `NOX_VAST_INSTANCE_ID=60509551` — scope to the intended instance where possible.

DO NOT expose secrets as process arguments or in logs. Do not grant account-wide deletion
or email access by default. The Google Drive connector inside ChatGPT is NOT a Drive
OAuth credential accessible to this server.

## Run locally on the NOX server

```sh
python3 nox-control/nox_integration_gateway.py status --provider all \
  --output /var/lib/nox/integrations/status.json
```

Only `connected` means the probe received an authenticated provider response.
`not_configured` means server authorization is still missing.
The status file contains only aggregate connectivity metadata (no Drive filenames).
Use a private local path, not a public web directory.

## Existing modules and scope

- `nox-control/nox_cold_drive.py`: separate SHA-256 checked model cold-store transfer
  with explicit `rclone` remote, no unattended delete. It must not be confused with
  the status gateway.
- `.github/workflows/nox-vast-direct-control.yml`: pre-existing owner-side
  Vast status/start/stop workflow. This gateway does not authorize these operations.
- Notion, GitHub and GitLab are authenticated with distinct narrowly scoped tokens.
- Mail, payments, personal Drive roots, and arbitrary web requests are **not**
  connected or granted by this bridge.

## Installation status

Source committed in GitHub. Not installed on Vast.ai and not authorized until
host-side deployment/credentials are explicitly verified. The owner must complete
OAuth/credential authorization in the provider's own flow. Do not assert LIVE
from GitHub source or from the connected ChatGPT integration alone.
