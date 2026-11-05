"""NOX Block 2: one P03 catalog and one approved UI file; no model installation proof.

Source-only guard. The native source and the UI discovery list must agree exactly,
and the Windows E06 packager must stage that exact Git blob. Never promote model
candidate metadata to approved downloads or assert Windows runtime acceptance.
"""
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODEL = "Packages/P03/Source/P03.ModelCenter/ModelCatalog.cs"
PREVIEW = "Packages/P03/Source/P03.ModelCenter.Wow/ui.js"
CATALOG = "Packages/P03/Source/python-host/catalog30.discovery.json"
PINS = "coordination/express/P03_PINNED_GIT_BLOBS.json"
BUILDER = "coordination/e06/build_onehost_installer.ps1"
REVIEWED = "contracts/p03_reviewed_artifacts.json"


def git_blob(path):
    result = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD:" + path],
                            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True)
    digest = result.stdout.strip().lower()
    if not re.fullmatch("[a-f0-9]{40}", digest):
        raise ValueError("INVALID_GIT_BLOB:" + path)
    return digest


def check():
    native = (ROOT / MODEL).read_text(encoding="utf-8")
    preview = (ROOT / PREVIEW).read_text(encoding="utf-8")
    # Seed is the offline placeholder, never a separate approval or downloader.
    match = re.search(r"^const familySeed = (\[.*?\]);", preview, re.MULTILINE)
    if match is None:
        raise ValueError("P03_PREVIEW_SEED_MISSING")
    seed = json.loads(match.group(1))
    native_ids = re.findall(r'Family\("([^"]+)",\s*"[^"]+"\)', native)
    ui_ids = [v[0] for v in seed]
    catalog = json.loads((ROOT / CATALOG).read_text(encoding="utf-8"))
    catalog_ids = [v["id"] for v in catalog["models"]]
    if not (len(native_ids) == len(ui_ids) == len(catalog_ids) == 31):
        raise ValueError("P03_31_FAMILY_COUNT_DRIFT")
    if len(set(native_ids)) != 31 or len(set(ui_ids)) != 31 or len(set(catalog_ids)) != 31:
        raise ValueError("P03_DUPLICATE_FAMILY")
    if native_ids != ui_ids or ui_ids != catalog_ids:
        raise ValueError("P03_NATIVE_UI_PYTHON_CATALOG_MISMATCH")
    if "qwen3-embedding" not in ui_ids or "qwen2.5-coder" not in ui_ids:
        raise ValueError("P03_BLOCK2_MODELS_MISSING")
    if catalog["sourceType"] != "discovery_only":
        raise ValueError("P03_UNREVIEWED_DOWNLOAD_BYPASS")
    if any(x["reviewStatus"] != "REVIEW_REQUIRED" or x["downloadEligible"] is not False
           for x in catalog["models"]):
        raise ValueError("P03_UNREVIEWED_ARTIFACT_AUTOPROMOTED")
    if catalog["sourceGitBlobSha1"] != git_blob(MODEL):
        raise ValueError("P03_PYTHON_SOURCE_PIN_DRIFT")
    ui_blob = git_blob(PREVIEW)
    pins = json.loads((ROOT / PINS).read_text(encoding="utf-8"))
    overrides = [x for x in pins.get("approved_overrides", []) if x["path"] == PREVIEW]
    if len(overrides) != 1 or overrides[0]["post_git_blob_sha1"] != ui_blob:
        raise ValueError("P03_OWNER_SOURCE_PIN_DRIFT")
    if overrides[0]["post_bytes"] != len((ROOT / PREVIEW).read_bytes()):
        raise ValueError("P03_OWNER_BYTES_DRIFT")
    builder = (ROOT / BUILDER).read_text(encoding="utf-8")
    if builder.count("relative='ui.js';blob='" + ui_blob + "'") != 1:
        raise ValueError("P03_WINDOWS_STAGE_UI_PIN_DRIFT")
    reviewed = json.loads((ROOT / REVIEWED).read_text(encoding="utf-8"))
    if reviewed.get("schema") != "NOX-P03-REVIEWED-ARTIFACTS-V1":
        raise ValueError("P03_NATIVE_REVIEW_REGISTRY_SCHEMA_DRIFT")
    if not isinstance(reviewed.get("items"), list):
        raise ValueError("P03_REVIEWED_ITEMS_INVALID")
    print("BLOCK2_P03_CATALOG_PIN_PASS 31_NATIVE_31_UI_31_ONEHOST_DISCOVERY_NOT_INSTALLED")


if __name__ == "__main__":
    try:
        check()
    except (OSError, KeyError, TypeError, IndexError, ValueError, subprocess.CalledProcessError) as exc:
        print("BLOCK2_P03_CATALOG_PIN_HOLD", str(exc), file=sys.stderr)
        sys.exit(2)
