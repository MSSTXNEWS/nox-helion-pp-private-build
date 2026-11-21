"""model_dl: download a model file with mandatory SHA256 verification. Explicit command only."""
import hashlib
import os
import urllib.error
import urllib.request
import registry as R
import web_fetch


@R.register("model_dl", "danger", {"properties": {
    "url": {"type": "string"}, "dest": {"type": "string"}, "sha256": {"type": "string"},
    "max_gb": {"type": "number", "default": 40}, "timeout": {"type": "integer", "default": 60}}, "required": ["url", "dest", "sha256"]},
    "Download to <dest>.part, verify SHA256, then rename. Domain allowlist (NOX_WEB_ALLOW). Refuses to overwrite. Needs confirm.")
def model_dl(a):
    web_fetch.check_url(a["url"])
    want = a["sha256"].lower()
    if len(want) != 64 or any(c not in "0123456789abcdef" for c in want):
        return R.fail("sha256 must be 64 hex chars")
    dest = R.safe_path(a["dest"])
    if os.path.exists(dest):
        return R.fail("dest exists: " + dest)
    part = dest + ".part"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    h, n, cap = hashlib.sha256(), 0, int(a["max_gb"] * 2**30)
    op = urllib.request.build_opener(web_fetch._NoRedirect)
    try:
        with op.open(urllib.request.Request(a["url"], headers={"User-Agent": "nox-selftools"}), timeout=a["timeout"]) as r, open(part, "wb") as f:
            for b in iter(lambda: r.read(1 << 20), b""):
                n += len(b)
                if n > cap:
                    raise ValueError("exceeds max_gb")
                h.update(b)
                f.write(b)
    except (urllib.error.URLError, OSError) as e:
        if os.path.exists(part):
            os.remove(part)
        if isinstance(e, urllib.error.HTTPError):
            return R.fail("HTTP %d" % e.code)
        return R.blocked("download failed: %s" % getattr(e, "reason", e), "network access to " + a["url"])
    except ValueError as e:
        os.remove(part)
        return R.fail(e)
    if h.hexdigest() != want:
        os.remove(part)
        return {"ok": False, "error": "sha256 mismatch", "expected": want, "got": h.hexdigest(), "bytes": n}
    os.replace(part, dest)
    return {"ok": True, "dest": dest, "bytes": n, "sha256": want}
