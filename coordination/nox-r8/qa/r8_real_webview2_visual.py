#!/usr/bin/env python3
"""NOX R8 installed WebView2 CDP visual witness (source + physical GUI, fail closed).

Does not install or start NOX, download browsers, change SQLite or claim release.
Requires the *real installed WebView2* with a localhost-only CDP endpoint already
enabled by the owner. Never attach an untrusted remote debugging endpoint.

Example:
  python tests/r8_real_webview2_visual.py --cdp http://127.0.0.1:9222 \
    --exe C:\NOX_HELION\NOX_NEW\release\NOX.HELION.exe \
    --expected-exe-sha <64 hex> --source-sha <40 hex> --out <output-dir>

Only a separate owner-side BUILD_RECEIPT and native B06/Windows E07 can accept
the complete release. This witness covers 8 original routes * 4 viewports *
2 reduced-motion settings = 64 measured PNGs, not actual training/voice.
"""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

VIEWPORTS = ((320, 720), (390, 844), (800, 480), (1920, 1080))
ROUTES = ("consciousness", "atlas", "reflection", "nexus", "forge",
          "core", "voice", "persona")
SCHEMA = "NOX_R8_WEBVIEW2_CDP_64_SCREENSHOT_V1"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for piece in iter(lambda: f.read(1024 * 1024), b""):
            h.update(piece)
    return h.hexdigest()


async def capture(args):
    # No cloud/browser download; attach only to existing WebView2 on localhost.
    u = urlsplit(args.cdp)
    if u.scheme != "http" or u.hostname not in ("127.0.0.1", "localhost") \
       or u.username or u.password or u.query or u.fragment or not u.port:
        raise RuntimeError("CDP_ENDPOINT_MUST_BE_EXPLICIT_LOCALHOST_HOLD")
    exe = args.exe.resolve(strict=True)
    actual_exe_hash = sha256_file(exe)
    if actual_exe_hash != args.expected_exe_sha.lower():
        raise RuntimeError("IMMUTABLE_EXE_SHA_MISMATCH_HOLD")

    # This is an installed binary witness. Absence of a pinned manifest is HOLD.
    manifest_path = exe.parent / "BUILD_RECEIPT.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if manifest.get("schema") != "NOX_R8_NATIVE_SINGLE_EXE_V1" or \
       str(manifest.get("exe_sha256", "")).lower() != actual_exe_hash or \
       str(manifest.get("source_git_sha", "")).lower() != args.source_sha.lower():
        raise RuntimeError("BUILD_RECEIPT_SOURCE_EXE_PARITY_HOLD")
    manifest_sha_before = sha256_file(manifest_path)

    try:
        from playwright.async_api import async_playwright
    except ImportError as error:
        raise RuntimeError("PLAYWRIGHT_PYTHON_NOT_INSTALLED_HOLD") from error

    evidence_root = args.out.resolve()
    if evidence_root.exists() and any(evidence_root.iterdir()):
        raise RuntimeError("EVIDENCE_TARGET_NOT_EMPTY_HOLD")
    evidence_root.mkdir(parents=True, exist_ok=True)
    screenshots = []
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(args.cdp, timeout=12000)
        try:
            candidates = []
            for context in browser.contexts:
                for page in context.pages:
                    try:
                        info = await asyncio.wait_for(page.evaluate("""() => ({
                          title: document.title,
                          routes: [...document.querySelectorAll('button.core[data-route]')]
                            .map(x => x.dataset.route),
                          hasHelion: !!document.getElementById('helionFx'),
                          hasStatus: !!document.getElementById('status'),
                        })"""), timeout=5)
                    except Exception:
                        continue
                    if info["title"] == "NOX HELION" and info["hasHelion"] and \
                       info["hasStatus"] and set(info["routes"]) == set(ROUTES) and \
                       len(info["routes"]) == len(ROUTES):
                        candidates.append(page)
            if len(candidates) != 1:
                raise RuntimeError("E07_WEBVIEW2_CDP_TARGET_NOT_UNIQUE_HOLD:"
                                   + str(len(candidates)))
            target = candidates[0]
            if target.is_closed():
                raise RuntimeError("E07_WEBVIEW2_TARGET_CLOSED_HOLD")

            for width, height in VIEWPORTS:
                await target.set_viewport_size({"width": width, "height": height})
                for reduced in (False, True):
                    await target.emulate_media(
                        reduced_motion="reduce" if reduced else "no-preference"
                    )
                    observed = await target.evaluate(
                        "() => matchMedia('(prefers-reduced-motion: reduce)').matches"
                    )
                    if observed is not reduced:
                        raise RuntimeError("WEBVIEW2_REDUCED_MOTION_MEDIA_QUERY_HOLD")
                    for route in ROUTES:
                        result = await target.evaluate("""route => {
                           const button = [...document.querySelectorAll('button.core[data-route]')]
                             .find(x => x.dataset.route === route);
                           if (!button || button.disabled) return {ok:false,why:'BUTTON_MISSING'};
                           button.click();
                           const active = [...document.querySelectorAll('.panel[data-panel].active')];
                           return {
                             ok: active.length===1 && active[0].dataset.panel===route &&
                                button.getAttribute('aria-current')==='page',
                             active: active.map(x=>x.dataset.panel),
                             role: button.getAttribute('aria-current'),
                             coreCount: document.querySelectorAll('button.core[data-route]').length,
                             documentWidth: document.documentElement.scrollWidth,
                             viewportWidth: window.innerWidth
                           };
                        }""", route)
                        if not result["ok"] or result["coreCount"] != 8:
                            raise RuntimeError("R8_ROUTE_UIA_PANEL_HOLD:" + route +
                                               ":" + json.dumps(result))
                        # Intentional screenshot of the real CDP target. Not a
                        # generated mock or screenshot of a detached HTML file.
                        out_path = evidence_root / (
                            f"r8_{width}x{height}_"
                            f"{'reduce' if reduced else 'normal'}_{route}.png"
                        )
                        await target.screenshot(path=str(out_path),
                                                full_page=False, animations="disabled")
                        if not out_path.is_file() or out_path.stat().st_size < 1000:
                            raise RuntimeError("SCREENSHOT_EMPTY_HOLD:" + route)
                        screenshots.append({
                            "path": out_path.name, "width": width, "height": height,
                            "reducedMotionCdpEmulated": reduced, "route": route,
                            "sha256": sha256_file(out_path), "bytes": out_path.stat().st_size
                        })
        finally:
            await browser.close()

    if len(screenshots) != 64:
        raise RuntimeError("EXPECTED_EXACTLY_64_REAL_SCREENSHOTS_HOLD")
    if sha256_file(exe) != actual_exe_hash or \
       sha256_file(manifest_path) != manifest_sha_before:
        raise RuntimeError("SOURCE_OR_EXE_MUTATED_DURING_VISUAL_TEST_HOLD")
    receipt = {
        "schema": SCHEMA, "status": "WEBVIEW2_VISUAL_SCOPE_PASS_ONLY",
        "releaseAccepted": False, "sourceGitSha": args.source_sha.lower(),
        "exeSha256": actual_exe_hash,
        "buildReceiptSha256": manifest_sha_before,
        "cdpEndpoint": args.cdp, "cdpPageSelectedByRealDom": True,
        "reducedMotion": "CDP_EMULATED_NOT_OWNER_OS_SETTING",
        "audioInput": "NOT_TESTED", "gpuTraining": "NOT_TESTED",
        "nativeIpcEffects": "NOT_TESTED", "ownerQwenStopSqlite": "NOT_TESTED",
        "screenshots": screenshots, "capturedAt": datetime.now(timezone.utc).isoformat(),
    }
    result_path = evidence_root / "WEBVIEW2_VISUAL_RECEIPT.json"
    result_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False),
                           encoding="utf-8")
    return result_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdp", required=True, help="Existing LOCAL WebView2 CDP endpoint")
    ap.add_argument("--exe", required=True, type=Path)
    ap.add_argument("--expected-exe-sha", required=True)
    ap.add_argument("--source-sha", required=True)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    if not re.fullmatch(r"[0-9a-fA-F]{64}", args.expected_exe_sha) or \
       not re.fullmatch(r"[0-9a-fA-F]{40}", args.source_sha):
        ap.error("Exact immutable source and EXE digests are mandatory")
    try:
        receipt = asyncio.run(capture(args))
    except Exception as error:
        print("NOX_R8_WEBVIEW2_VISUAL_HOLD: " + str(error), file=sys.stderr)
        return 2
    print("WEBVIEW2_VISUAL_SCOPE_PASS_ONLY: " + str(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
