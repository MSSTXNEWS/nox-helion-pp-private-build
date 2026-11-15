#!/usr/bin/env python3
"""NOX R2 connection preflight. Read-only. No cloud mutations or leaked credentials.

Supply RCLONE_CONFIG_NOXDRIVE_ACCESS_KEY_ID and
RCLONE_CONFIG_NOXDRIVE_SECRET_ACCESS_KEY only through an approved local secret
manager or authenticated runner. Do not paste credentials in chat/logs.
"""
import json
import os
import re
import subprocess
import sys

ENDPOINT = "https://6ab1503ad55d0a429062ad470c448012.r2.cloudflarestorage.com"
BUCKET = "123"
REMOTE_NAME = "noxdrive"
SAFE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,62}$")


def configure_environment(env):
    env = dict(env)
    # rclone supports environment-based remotes without writing rclone.conf.
    opts = {"TYPE": "s3", "PROVIDER": "Cloudflare", "REGION": "auto",
            "ENDPOINT": ENDPOINT, "NO_CHECK_BUCKET": "true",
            "ACL": "private", "ENV_AUTH": "false"}
    for key, value in opts.items():
        env["RCLONE_CONFIG_NOXDRIVE_" + key] = value
    if not env.get("RCLONE_CONFIG_NOXDRIVE_ACCESS_KEY_ID") or not env.get(
        "RCLONE_CONFIG_NOXDRIVE_SECRET_ACCESS_KEY"
    ):
        raise RuntimeError("HOLD_CREDENTIALS_NOT_CONFIGURED")
    return env


def main():
    if not SAFE.fullmatch(BUCKET):
        raise RuntimeError("HOLD_INVALID_BUCKET")
    env = configure_environment(os.environ)
    # Never print rclone error streams: they can include provider configuration.
    try:
        probe = subprocess.run(
            ["rclone", "lsf", "--max-depth", "1", "--files-only",
             "--format", "p", f"{REMOTE_NAME}:{BUCKET}"],
            env=env, capture_output=True, text=True, timeout=60, check=False)
    except FileNotFoundError:
        raise RuntimeError("HOLD_RCLONE_MISSING") from None
    except subprocess.TimeoutExpired:
        raise RuntimeError("HOLD_R2_TIMEOUT") from None
    if probe.returncode:
        raise RuntimeError("HOLD_R2_AUTH_OR_BUCKET_ACCESS") from None
    # No filenames, keys or payloads in output. The bucket can be empty.
    print(json.dumps({"schema": "NOX_R2_PREFLIGHT_V1",
                      "bucket": BUCKET, "endpoint_configured": True,
                      "read_access": "PASS",
                      "write_access": "NOT_TESTED",
                      "content_integrity": "NOT_TESTED",
                      "transferred_bytes": 0,
                      "server_cleanup": "NOT_STARTED"}))


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
