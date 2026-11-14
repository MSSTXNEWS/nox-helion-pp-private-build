"""ONEPASS read-only Vast instance discovery via OFFICIAL vastai CLI and SDK.

Two independent supported client surfaces instead of homemade guessed URLs.
No instance creation, SSH, writes, deletion, restart, payment, or credential
logging. Only the same NOX2 secret stored in GitHub Actions is read from env.
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import sys
from typing import Any

TARGET_ID = 60509551
MAX_ITEMS = 10000
URL_WORDS = ("http", "https", "ssh", "token", "secret", "key")


def normalize_instances(payload: Any) -> list[dict]:
    if isinstance(payload, dict):
        payload = payload.get("instances", payload.get("data", payload.get("result")))
    if not isinstance(payload, list) or len(payload) > MAX_ITEMS:
        raise ValueError("HOLD_INSTANCE_LIST_SCHEMA")
    if not all(isinstance(item, dict) for item in payload):
        raise ValueError("HOLD_INSTANCE_ITEMS_SCHEMA")
    return payload


def classify_failure(output: str) -> str:
    match = re.search(r"(?i)(?:HTTP\s*[:=]?\s*|status\s*[:=]?\s*)(40[0-9]|429|50[0-9])\b", output[:10000])
    if match:
        return "HTTP_" + match.group(1)
    match = re.search(r"(?<!\d)(401|403|404|429|500|502|503|504)(?!\d)", output[:2000])
    return "HTTP_" + match.group(1) if match else "CLIENT_ERROR"


def safe_summary(source: str, payload: Any) -> dict:
    items = normalize_instances(payload)
    selected = [obj for obj in items if str(obj.get("id")) == str(TARGET_ID)]
    status = "NO_MATCH" if not selected else str(selected[0].get("actual_status", "unknown"))[:32]
    if not re.fullmatch(r"[a-zA-Z_\-]{1,32}", status):
        status = "UNKNOWN_FORMAT"
    return {
        "client": source,
        "state": "TARGET_VISIBLE" if selected else "HOLD_TARGET_NOT_VISIBLE",
        "target_id": TARGET_ID,
        "target_count": len(selected),
        "total_count": len(items),
        "target_state": status,
        "read_only": True,
        "instance_mutation": False,
        "secrets_exported": False,
    }


def command_readonly(label: str, command: list[str]) -> dict:
    if any(x in command for x in ("stop", "destroy", "start", "create", "reboot", "launch", "--api-key", "set")):
        raise RuntimeError("HOLD_FORBIDDEN_CLI_OPERATION")
    env = dict(os.environ)
    env["VAST_API_KEY"] = os.environ.get("NOX2", "")
    if not env["VAST_API_KEY"]:
        return {"client": label, "state": "HOLD_NOX2", "read_only": True}
    try:
        completed = subprocess.run(command, text=True, capture_output=True, timeout=55, env=env, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {"client": label, "state": "HOLD_CLIENT_UNAVAILABLE_OR_TIMEOUT", "read_only": True}
    if completed.returncode != 0:
        return {"client": label, "state": "HOLD_" + classify_failure(completed.stderr or completed.stdout),
                "read_only": True}
    try:
        return safe_summary(label, json.loads(completed.stdout))
    except (ValueError, json.JSONDecodeError):
        return {"client": label, "state": "HOLD_JSON_OR_SCHEMA", "read_only": True}


def main() -> int:
    sdk = [
        sys.executable, "-c",
        "import json; from vastai import VastAI; print(json.dumps(VastAI().show_instances()))",
    ]
    cli = ["vastai", "show", "instances", "--raw"]
    results = [command_readonly("OFFICIAL_PYTHON_SDK", sdk),
               command_readonly("OFFICIAL_VASTAI_CLI", cli)]
    for result in results:
        print("NOX_VAST_ONEPASS=" + json.dumps(result, sort_keys=True, separators=(",", ":")))
    visible = [r for r in results if r["state"] == "TARGET_VISIBLE"]
    if visible:
        print("NOX_VAST_ACCESS_RECOVERED=true")
        return 0
    print("NOX_VAST_ACCESS_RECOVERED=false")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
