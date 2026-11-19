"""NOX WEB V29.3 non-destructive acceptance gate.
Never promotes PUBLIC PREVIEW, changes model weights or sends a STOP command.
Use behind an authenticated OneHost tunnel; do not expose it on a public endpoint.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit

REQUIRED = (
    "/api/nox/status",
    "/api/nox/chat/stream",
    "/api/nox/stop",
)

def request(base: str, path: str, method: str = "GET", cookie: str = "", body: bytes | None = None):
    headers = {"Accept": "application/json", "User-Agent": "NOX-V109-ACCEPTANCE"}
    if cookie:
        headers["Cookie"] = cookie
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base.rstrip("/") + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status, resp.headers, resp.read(8192)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read(8192)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://127.0.0.1:8080")
    p.add_argument("--matrix", default="coordination/NOX_V98_WEB_FULL_REAL_API_MATRIX.json")
    p.add_argument("--authorized", action="store_true", help="Read-only authorized status test; requires NOX_SESSION_COOKIE")
    args = p.parse_args()
    dest = urlsplit(args.base)
    if dest.hostname not in ("127.0.0.1", "localhost", "::1") or dest.scheme != "http" or dest.username or dest.password:
        raise SystemExit("HOLD_ONLY_LOCAL_ONEHOST_ENDPOINT_ALLOWED")
    with open(args.matrix, encoding="utf-8") as f:
        matrix = json.load(f)
    routes = {item["route"] for item in matrix["functions"]}
    assert set(REQUIRED).issubset(routes), "Critical V29 routes absent from frozen frontend matrix"
    report = {"schema": "NOX_V109_WEB_ACCEPTANCE_V1",
              "referenced_routes": len(routes), "critical_routes": {},
              "owner_authenticated": False, "stream_e2e_pass": False,
              "s03_e2e_pass": False, "stop_e2e_pass": False,
              "full_web_release_allowed": False}
    # No unauthorized request is allowed to reach a model or trigger STOP.
    for path, method in (("/api/nox/status", "GET"),
                         ("/api/nox/chat/stream", "POST"),
                         ("/api/nox/stop", "POST")):
        status, _, _ = request(args.base, path, method, body=b"{}" if method == "POST" else None)
        report["critical_routes"][path] = {
            "anonymous_http": status,
            "anonymous_auth_rejected": status in (401, 403),
            "route_existence_verified": False,  # 401/403 can originate in global auth middleware
            "feature_e2e_pass": False,
        }
    cookie = os.environ.get("NOX_SESSION_COOKIE", "")
    if args.authorized and not cookie:
        report["hold"] = "NOX_SESSION_COOKIE_MISSING"
    elif args.authorized:
        code, headers, body = request(args.base, "/api/nox/status", cookie=cookie)
        info = {}
        if code == 200:
            try: info = json.loads(body)
            except (ValueError, UnicodeDecodeError): pass
        report["owner_authenticated"] = (
            code == 200 and info.get("backend") == "EXISTING_NATIVE_ONEHOST"
            and info.get("native_p02_bound") is True
        )
        report["authorized_status_http"] = code
    report["dialog_scope_e2e_pass"] = False
    report["frontend_v29_dialog_id_bridge_compatible"] = False
    report["gate"] = "HOLD_FULL_REAL_E2E"
    # An authenticated status alone never establishes generation, memory or STOP safety.
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if all(v["anonymous_auth_rejected"] for v in report["critical_routes"].values()) else 2

if __name__ == "__main__":
    sys.exit(main())
