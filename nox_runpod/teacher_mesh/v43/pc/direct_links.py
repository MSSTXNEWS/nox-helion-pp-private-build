"""NOX V43 Cold Vault direct links, upstream SHA gate, and opt-in PC-only download.

Read-only by default. No Vast.ai writes, no second OneHost, no model promotion.
An owner may explicitly download to PC Cold Vault after remote metadata/space checks.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import urllib.parse
import urllib.request

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CATALOG = REPO_ROOT / "coordination" / "NOX_DIRECT_DOWNLOAD_LINKS_20261114.json"
V43_CATALOG = Path(__file__).resolve().parents[1] / "models.v43.json"
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
REV_RE = re.compile(r"^[0-9a-f]{40}$")
NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,160}$")
ID_RE = re.compile(r"^[a-z0-9-]{3,70}$")
REPO_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
MAX_BYTES_METADATA = 5_000_000
RESERVE_BYTES = 12_000_000_000
SNAPSHOT_PATTERNS = (
    "model.safetensors", "*.safetensors.index.json", "config.json",
    "generation_config.json", "tokenizer*", "*.model", "merges.txt",
    "vocab.json", "special_tokens_map.json", "preprocessor_config.json",
    "processor_config.json", "feature_extractor_config.json",
    "normalizer.json", "chat_template.jinja", "modules.json",
    "sentence_bert_config.json", "config_sentence_transformers.json",
)


def digest_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_catalog(path: Path = DEFAULT_CATALOG, v43_path: Path = V43_CATALOG) -> dict:
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    if obj.get("schema") != "NOX_DIRECT_DOWNLOAD_LINKS_V1":
        raise ValueError("HOLD_LINK_SCHEMA")
    if obj.get("instance_id") != 60509551:
        raise ValueError("HOLD_WRONG_INSTANCE")
    files = obj.get("files")
    if not isinstance(files, list) or not 1 <= len(files) <= 16:
        raise ValueError("HOLD_LINK_COUNT")
    refs = json.loads(Path(v43_path).read_text(encoding="utf-8"))["models"]
    existing = {m["source_repo"] + "/" + m["source_file"]: m["sha256"]
                for m in refs if m["method"] == "single_file"}
    seen = set()
    for f in files:
        if not isinstance(f, dict):
            raise ValueError("HOLD_FILE_OBJECT")
        model_id = f.get("id")
        sha = f.get("expected_sha256")
        if not isinstance(model_id, str) or not ID_RE.fullmatch(model_id) or model_id in seen:
            raise ValueError("HOLD_ID")
        seen.add(model_id)
        if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
            raise ValueError("HOLD_SHA")
        url = f.get("url")
        if not isinstance(url, str):
            raise ValueError("HOLD_URL")
        parsed = urllib.parse.urlsplit(url)
        if (parsed.scheme != "https" or parsed.netloc != "huggingface.co"
                or parsed.query or parsed.fragment or "%" in parsed.path):
            raise ValueError("HOLD_URL_ORIGIN")
        path_bits = parsed.path.strip("/").split("/")
        if len(path_bits) != 5 or path_bits[2:4] != ["resolve", "main"]:
            raise ValueError("HOLD_URL_PATH")
        repo = "/".join(path_bits[:2])
        name = path_bits[4]
        if not REPO_RE.fullmatch(repo) or not NAME_RE.fullmatch(name):
            raise ValueError("HOLD_REPO_OR_NAME")
        f["source_repo"] = repo
        f["filename"] = name
        if repo + "/" + name in existing and sha != existing[repo + "/" + name]:
            raise ValueError("HOLD_V43_HASH_DRIFT")
        if f.get("requires_repo_snapshot") and not name.endswith(".safetensors"):
            raise ValueError("HOLD_SNAPSHOT_CLASS")
    if obj.get("policy", {}).get("no_auto_download") is not True:
        raise ValueError("HOLD_AUTOMATION_POLICY")
    return obj


def _remote_json(url: str) -> dict:
    request = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": "NOX-ColdVault/43"},
        method="GET")
    with urllib.request.urlopen(request, timeout=20) as response:
        body = response.read(MAX_BYTES_METADATA + 1)
    if len(body) > MAX_BYTES_METADATA:
        raise ValueError("HOLD_UPSTREAM_RESPONSE_LIMIT")
    result = json.loads(body)
    if not isinstance(result, dict):
        raise ValueError("HOLD_UPSTREAM_NOT_OBJECT")
    return result


def upstream_receipt(entry: dict, *, metadata_fetch=None) -> dict:
    """Resolve immutable HF commit + metadata content SHA. No weight bytes fetched."""
    repo = entry["source_repo"]
    name = entry["filename"]
    meta_url = "https://huggingface.co/api/models/" + repo + "/revision/main?blobs=true"
    try:
        meta = (metadata_fetch or _remote_json)(meta_url)
    except Exception:
        return {"id": entry["id"], "state": "HOLD_UPSTREAM_UNAVAILABLE"}
    rev = meta.get("sha")
    if not isinstance(rev, str) or not REV_RE.fullmatch(rev):
        return {"id": entry["id"], "state": "HOLD_REVISION_NOT_PINNED"}
    sibs = meta.get("siblings")
    if not isinstance(sibs, list):
        return {"id": entry["id"], "state": "HOLD_NO_FILE_METADATA"}
    match = next((x for x in sibs if isinstance(x, dict) and
                  x.get("rfilename") == name), None)
    if match is None:
        return {"id": entry["id"], "state": "HOLD_FILE_NOT_FOUND"}
    lfs = match.get("lfs") or {}
    upstream_sha = lfs.get("sha256") if isinstance(lfs, dict) else None
    if not isinstance(upstream_sha, str) or not SHA_RE.fullmatch(upstream_sha):
        return {"id": entry["id"], "state": "HOLD_UPSTREAM_SHA_UNAVAILABLE",
                "revision": rev}
    if upstream_sha != entry["expected_sha256"]:
        return {"id": entry["id"], "state": "HOLD_UPSTREAM_SHA_MISMATCH",
                "revision": rev}
    return {
        "id": entry["id"], "state": "UPSTREAM_SHA_VERIFIED",
        "revision": rev, "expected_sha256": upstream_sha,
        "pinned_url": ("https://huggingface.co/" + repo + "/resolve/" + rev + "/" + name),
        "metadata_only": True, "file_downloaded": False,
    }


def cold_status(entry: dict, root: Path) -> dict:
    folder = Path(root) / entry["id"]
    item = folder / entry["filename"]
    if item.exists():
        if not item.is_file() or item.is_symlink():
            return {"id": entry["id"], "state": "HOLD_INVALID_LOCAL_PATH"}
        return {"id": entry["id"], "state": "SKIP_SHA_VERIFIED" if
                digest_file(item) == entry["expected_sha256"] else "HOLD_LOCAL_HASH_MISMATCH"}
    if folder.exists() and any(folder.iterdir()) and not entry.get("requires_repo_snapshot"):
        return {"id": entry["id"], "state": "HOLD_EXISTING_PARTIAL_OR_UNKNOWN_DIR"}
    return {"id": entry["id"], "state": "MISSING"}


def download_to_pc(entry: dict, root: Path, *, metadata_fetch=None,
                   file_download=None, snapshot_download=None,
                   free_bytes=None) -> dict:
    """Explicit opt-in; only existing local Cold Vault. No overwrite or promotion."""
    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        return {"id": entry["id"], "state": "HOLD_PC_COLD_ROOT_MISSING"}
    status = cold_status(entry, root)
    if status["state"] != "MISSING":
        return status
    try:
        free = int(free_bytes) if free_bytes is not None else shutil.disk_usage(root).free
    except (OSError, ValueError, TypeError):
        return {"id": entry["id"], "state": "HOLD_PC_FREE_SPACE_UNKNOWN"}
    size = entry.get("size_gb_approx")
    if not isinstance(size, (int, float)) or size <= 0:
        return {"id": entry["id"], "state": "HOLD_SIZE_UNKNOWN"}
    if free < int(size * 1_100_000_000) + RESERVE_BYTES:
        return {"id": entry["id"], "state": "HOLD_PC_DISK_RESERVE"}
    receipt = upstream_receipt(entry, metadata_fetch=metadata_fetch)
    if receipt["state"] != "UPSTREAM_SHA_VERIFIED":
        return receipt
    if file_download is None or snapshot_download is None:
        return {"id": entry["id"], "state": "HOLD_HF_DOWNLOADER_MISSING"}
    folder = root / entry["id"]
    if folder.exists() and folder.is_symlink():
        return {"id": entry["id"], "state": "HOLD_SYMLINK_FOLDER"}
    folder.mkdir(exist_ok=True)
    revision = receipt["revision"]
    try:
        if entry.get("requires_repo_snapshot"):
            snapshot_download(
                repo_id=entry["source_repo"], revision=revision,
                local_dir=str(folder), allow_patterns=SNAPSHOT_PATTERNS)
        else:
            file_download(repo_id=entry["source_repo"], filename=entry["filename"],
                          revision=revision, local_dir=str(folder))
    except Exception:
        return {"id": entry["id"], "state": "HOLD_TRANSFER_INCOMPLETE"}
    item = folder / entry["filename"]
    if not item.is_file() or item.is_symlink() or digest_file(item) != entry["expected_sha256"]:
        return {"id": entry["id"], "state": "HOLD_DOWNLOADED_SHA_MISMATCH"}
    if entry.get("requires_repo_snapshot") and not (folder / "config.json").is_file():
        return {"id": entry["id"], "state": "HOLD_SNAPSHOT_CONFIG_MISSING"}
    files = []
    if entry.get("requires_repo_snapshot"):
        for f in sorted(folder.rglob("*")):
            if f.is_file() and not f.is_symlink() and ".cache" not in f.parts:
                files.append({"name": f.relative_to(folder).as_posix(),
                              "bytes": f.stat().st_size, "sha256": digest_file(f)})
    else:
        files.append({"name": entry["filename"], "bytes": item.stat().st_size,
                      "sha256": entry["expected_sha256"]})
    receipt_path = folder / "NOX_DIRECT_LINK_RECEIPT.json"
    if receipt_path.exists():
        return {"id": entry["id"], "state": "HOLD_RECEIPT_EXISTS"}
    payload = {"schema": "NOX_COLD_DOWNLOAD_RECEIPT_V1", "id": entry["id"],
               "revision": revision, "files": files, "source_verified": True,
               "model_activated": False, "weights_trained": False,
               "vast_changed": False}
    with receipt_path.open("x", encoding="utf-8") as out:
        json.dump(payload, out, ensure_ascii=False, indent=2)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())
    return {"id": entry["id"], "state": "PC_COLD_DOWNLOADED_SHA_VERIFIED",
            "revision": revision, "files": len(files)}


def main(argv=None) -> int:
    arg = argparse.ArgumentParser(description="NOX Cold Vault verified direct links")
    arg.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    arg.add_argument("--root", type=Path,
                     default=Path(r"C:\NOX_HELION\MODEL_VAULT") if os.name == "nt"
                     else Path.home() / "NOX_HELION" / "MODEL_VAULT")
    arg.add_argument("--ids", nargs="*")
    arg.add_argument("--verify-upstream", action="store_true")
    arg.add_argument("--audit-local", action="store_true")
    arg.add_argument("--download", action="store_true",
                     help="Explicit opt-in PC Cold Vault download, never Vast")
    a = arg.parse_args(argv)
    try:
        obj = load_catalog(a.catalog)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as ex:
        print("HOLD_CATALOG_" + type(ex).__name__)
        return 2
    items = obj["files"]
    if a.ids:
        items = [x for x in items if x["id"] in a.ids]
        if len(items) != len(set(a.ids)):
            print("HOLD_UNKNOWN_MODEL_ID")
            return 2
    if a.download and not a.ids:
        print("HOLD_EXPLICIT_MODEL_IDS_REQUIRED")
        return 2
    hf_file = hf_snapshot = None
    if a.download:
        if os.name != "nt":
            print("HOLD_PC_WINDOWS_ONLY")
            return 2
        try:
            from huggingface_hub import hf_hub_download, snapshot_download
            hf_file, hf_snapshot = hf_hub_download, snapshot_download
        except ImportError:
            print("HOLD_INSTALL_HUGGINGFACE_HUB")
            return 2
    failed = False
    for item in items:
        if a.download:
            result = download_to_pc(item, a.root, file_download=hf_file,
                                    snapshot_download=hf_snapshot)
        elif a.verify_upstream:
            result = upstream_receipt(item)
        elif a.audit_local:
            result = cold_status(item, a.root)
        else:
            result = {"id": item["id"], "state": "CATALOG_URL_ONLY",
                      "url": item["url"], "sha256": item["expected_sha256"],
                      "needs_full_snapshot": item.get("requires_repo_snapshot", False)}
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if result["state"].startswith("HOLD_"):
            failed = True
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
