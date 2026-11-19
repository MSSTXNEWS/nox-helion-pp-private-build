# Installed web asset inspection (read-only)

This inspector is source-only. It is not installed or run against production by this change. It fails closed unless the operator supplies a fresh owner receipt binding PID `356735`, process start ticks, UID, executable, explicit static-root argument, owner lease and STOP clearance, manifest, loopback origin, route prefix, and exact JS/CSS allowlist.

The receipt must be a regular file owned by the web process UID, not group/world writable, and no larger than 16 KiB. `issued_at` is Unix seconds and must be no more than five minutes old. `owner_lease` and `stop` must both equal `CLEAR`. The static root and every asset path component must exist without symlinks. The manifest is capped at 256 KiB and 128 allowlisted assets; each JS/CSS asset is capped at 10 MiB. Inspection hashes the bounded manifest, hashes each installed asset, performs a direct unauthenticated HTTP GET to the numeric loopback origin for each allowlisted asset, and requires the served bytes to match disk. Redirects, cookies, non-loopback origins, query strings, and oversized bodies are rejected.

Example receipt shape (values are illustrative and must be replaced with a newly authorized owner observation):

```json
{
  "pid": 356735,
  "start_ticks": 123456,
  "uid": 1001,
  "issued_at": 1795080000,
  "owner_lease": "CLEAR",
  "stop": "CLEAR",
  "entrypoint": "/usr/bin/node",
  "static_root": "/srv/nox/web",
  "manifest_rel": "asset-manifest.json",
  "serve_origin": "http://127.0.0.1:18775",
  "route_prefix": "/nox-web-v29",
  "allowlist": ["assets/chat.js", "assets/chat.css"]
}
```

Run only after owner authorization and a fresh receipt:

```sh
python -m nox_runpod.teacher_mesh.v77.installed_web_asset_inspector --receipt /path/to/owner-receipt.json
```

The program does not read `/proc/PID/environ`, print argv, make authenticated requests, modify files, or restart processes. A `HOLD` result is not an inspection pass. No claim about current live root or installed asset SHA is made until an authorized operator runs it and preserves the receipt/output.
