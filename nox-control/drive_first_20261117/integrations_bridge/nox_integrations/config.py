"""Server-owned configuration. Secret values never appear in repr/status."""
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import shutil
import stat

from .core import BridgeError

KEYS = frozenset({
    "NOX_DRIVE_REMOTE", "NOX_DRIVE_ROOT", "NOX_RCLONE_BIN", "NOX_RCLONE_CONFIG",
    "RCLONE_CONFIG_PASS", "NOX_ARTIFACT_ROOT", "NOX_DRIVE_CACHE_ROOT",
    "NOX_NOTION_TOKEN", "NOX_GITHUB_TOKEN", "NOX_GITLAB_TOKEN",
    "NOX_GITHUB_REPO", "NOX_GITLAB_PROJECT", "NOX_NOTION_VERSION",
    "NOX_GITHUB_API_VERSION", "NOX_DOWNLOAD_MAX_BYTES", "NOX_UPLOAD_MAX_BYTES",
    "NOX_CACHE_HEADROOM_BYTES", "NOX_TRANSFER_TIMEOUT_SECONDS",
    "NOX_ALLOW_DISK_CACHE",
})
TOKEN_KEYS = ("NOX_NOTION_TOKEN", "NOX_GITHUB_TOKEN", "NOX_GITLAB_TOKEN", "RCLONE_CONFIG_PASS")


def relative_path(value, *, allow_empty=False):
    if not isinstance(value, str) or len(value.encode("utf-8")) > 2048:
        raise BridgeError("INVALID_RELATIVE_PATH")
    if not value and allow_empty:
        return ""
    if (not value or value.startswith("/") or "\\" in value or ":" in value
            or any(ord(c) < 32 or ord(c) == 127 for c in value)
            or any(p in ("", ".", "..") for p in value.split("/"))):
        raise BridgeError("INVALID_RELATIVE_PATH")
    return value


def _private_json(path):
    """Open the existing owner-only JSON without following a leaf symlink."""
    path = Path(path)
    if not path.is_absolute():
        raise BridgeError("SECRET_FILE_MUST_BE_ABSOLUTE")
    current=Path("/")
    for part in path.parts[1:-1]:
        current=current/part
        if current.is_symlink():
            raise BridgeError("SECRET_FILE_SYMLINK_PARENT")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        raise BridgeError("SECRET_FILE_UNAVAILABLE") from None
    try:
        s = os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or stat.S_IMODE(s.st_mode) != 0o600 or s.st_uid != os.geteuid():
            raise BridgeError("SECRET_FILE_REQUIRES_OWNER_MODE_0600")
        if s.st_size > 65536:
            raise BridgeError("SECRET_FILE_TOO_LARGE")
        raw = os.read(fd, 65537)
        if len(raw) > 65536:
            raise BridgeError("SECRET_FILE_TOO_LARGE")
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeError):
            raise BridgeError("SECRET_FILE_INVALID_JSON") from None
        if not isinstance(data, dict) or any(k not in KEYS or not isinstance(v, str) for k, v in data.items()):
            raise BridgeError("SECRET_FILE_INVALID_KEYS_OR_TYPES")
        return data
    finally:
        os.close(fd)


@dataclass(repr=False)
class Config:
    values: dict = field(repr=False)

    @classmethod
    def load(cls, environ=None):
        env = os.environ if environ is None else environ
        data = _private_json(env["NOX_INTEGRATIONS_SECRETS_FILE"]) if env.get("NOX_INTEGRATIONS_SECRETS_FILE") else {}
        data.update({k: env[k] for k in KEYS if k in env})
        if any(not isinstance(v, str) or "\x00" in v for v in data.values()):
            raise BridgeError("INVALID_CONFIG")
        return cls(data)

    def __repr__(self):
        return "Config(<server-owned values hidden>)"

    def get(self, key, default=""):
        return self.values.get(key, default)

    def positive_int(self, key, default):
        raw = self.get(key, str(default))
        if not re.fullmatch(r"[0-9]{1,16}", raw) or not 0 < int(raw) <= 2**53:
            raise BridgeError("INVALID_CONFIG_INTEGER")
        return int(raw)

    @property
    def secrets(self):
        return tuple(self.get(k) for k in TOKEN_KEYS if self.get(k))

    def reject_secrets(self, value):
        if isinstance(value,dict):
            for k,v in value.items():
                self.reject_secrets(k);self.reject_secrets(v)
            return
        if isinstance(value,(list,tuple)):
            for v in value:
                self.reject_secrets(v)
            return
        if isinstance(value,str) and any(secret in value for secret in self.secrets):
            raise BridgeError("SECRET_IN_PAYLOAD")

    def redact(self, value):
        if isinstance(value, str):
            for secret in self.secrets:
                value = value.replace(secret, "[REDACTED]")
            return value
        if isinstance(value, list):
            return [self.redact(x) for x in value]
        if isinstance(value, dict):
            return {str(k): self.redact(v) for k, v in value.items()}
        return value

    def rclone_binary(self):
        configured = self.get("NOX_RCLONE_BIN")
        if configured:
            if not os.path.isabs(configured):
                raise BridgeError("RCLONE_BINARY_MUST_BE_ABSOLUTE")
            return configured if os.path.isfile(configured) and os.access(configured, os.X_OK) else ""
        return shutil.which("rclone") or ""

    def rclone_config(self):
        return self.get("NOX_RCLONE_CONFIG", str(Path.home() / ".config/rclone/rclone.conf"))

    def drive_requirements(self):
        return {
            "remote_configured": bool(self.get("NOX_DRIVE_REMOTE")),
            "project_root_configured": bool(self.get("NOX_DRIVE_ROOT")),
            "rclone_binary_present": bool(self.rclone_binary()),
            "existing_rclone_config_present": Path(self.rclone_config()).is_file(),
        }
