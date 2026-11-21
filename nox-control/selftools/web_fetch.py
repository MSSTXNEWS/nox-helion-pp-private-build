"""web_fetch: GET with domain allowlist (https only unless NOX_WEB_ALLOW_HTTP=1), size cap."""
import os
import urllib.error
import urllib.parse
import urllib.request
import registry as R

DEFAULT_ALLOW = ["api.github.com", "github.com", "raw.githubusercontent.com", "huggingface.co",
                 "pypi.org", "docs.python.org", "arxiv.org"]


def allow_hosts():
    env = os.environ.get("NOX_WEB_ALLOW")
    return [h.strip().lower() for h in env.split(",") if h.strip()] if env else DEFAULT_ALLOW


def check_url(url):
    u = urllib.parse.urlparse(url)
    http_ok = os.environ.get("NOX_WEB_ALLOW_HTTP") == "1"
    if u.scheme != "https" and not (http_ok and u.scheme == "http"):
        raise R.Denied("only https allowed")
    h = (u.hostname or "").lower()
    if not any(h == d or h.endswith("." + d) for d in allow_hosts()):
        raise R.Denied("domain not in allowlist: %s" % h)
    return u


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)  # redirects must stay inside the allowlist
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@R.register("web_fetch", "read", {"properties": {
    "url": {"type": "string"}, "max_bytes": {"type": "integer", "default": 200000}, "timeout": {"type": "integer", "default": 20}},
    "required": ["url"]}, "HTTP GET from allowlisted domains only (env NOX_WEB_ALLOW), redirects re-checked, size capped.")
def web_fetch(a):
    check_url(a["url"])
    op = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(a["url"], headers={"User-Agent": "nox-selftools"})
    try:
        with op.open(req, timeout=a["timeout"]) as r:
            raw = r.read(a["max_bytes"] + 1)
            return {"ok": True, "status": r.status, "content_type": r.headers.get("Content-Type"),
                    "truncated": len(raw) > a["max_bytes"], "text": raw[:a["max_bytes"]].decode("utf-8", "replace")}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": "HTTP %d" % e.code, "status": e.code}
    except (urllib.error.URLError, OSError) as e:
        return R.blocked("network unreachable: %s" % getattr(e, "reason", e), "network/proxy access to the host")
