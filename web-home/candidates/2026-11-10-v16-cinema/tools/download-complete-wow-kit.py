#!/usr/bin/env python3
"""NOX V19 extended vendor intake. Download source tarballs, not silently install.
Pinned runtime manifests are generated from the npm registry's resolved versions,
including SHA-256, exact package version, URL, and license/provenance evidence.
NO scripts from downloaded packages are executed.
"""
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import tarfile
import time

OUT = pathlib.Path(os.environ.get("NOX_VENDOR_OUT", "/tmp/nox-v19-extended")).resolve()
DIST = OUT / "packages"
META = OUT / "metadata"
DIST.mkdir(parents=True, exist_ok=True)
META.mkdir(parents=True, exist_ok=True)

# These are optional downloadable candidate resources, not claims of application integration.
PACKAGES = {
 "cinema": ["video.js", "plyr", "hls.js", "dashjs", "shaka-player", "wavesurfer.js"],
 "cinematic_visual": ["three", "postprocessing", "ogl", "pixi.js", "lottie-web", "gsap", "motion", "swiper", "@tsparticles/engine", "@tsparticles/slim", "@tsparticles/basic"],
 "maps_weather": ["leaflet", "leaflet.heat", "maplibre-gl", "ol", "@turf/turf"],
 "books_documents": ["pdfjs-dist", "epubjs", "marked", "highlight.js", "dompurify", "@mozilla/readability", "jszip"],
 "news_search": ["rss-parser", "fast-xml-parser", "sanitize-html", "fuse.js"],
 "notifications": ["web-push", "workbox-window", "workbox-sw", "idb", "dexie"],
 "calendar": ["fullcalendar", "@fullcalendar/core", "@fullcalendar/daygrid", "@fullcalendar/timegrid", "@fullcalendar/interaction"],
 "analytics": ["echarts", "uplot", "chart.js"],
 "glass_interface": ["photoswipe", "@shoelace-style/shoelace", "@floating-ui/dom", "@tabler/icons", "lit"],
}
# Don't run install scripts or launch network services.
errors = []
rows = []
for group, names in PACKAGES.items():
 for name in names:
  start = time.monotonic()
  result = {"group": group, "package": name, "role": "DOWNLOADED_CANDIDATE_NOT_RUNTIME_INTEGRATED"}
  try:
   query = subprocess.run(["npm", "view", name, "version", "license", "--json"],
                          capture_output=True, text=True, timeout=50, check=True)
   info = json.loads(query.stdout)
   if not isinstance(info, dict) or not info.get("version"):
    raise ValueError("npm view did not return a usable version")
   version = info["version"]
   result["version"] = version
   result["license"] = info.get("license", "UNVERIFIED")
   cmd = subprocess.run(["npm", "pack", f"{name}@{version}", "--pack-destination", str(DIST),
                         "--ignore-scripts", "--json"],
                        capture_output=True, text=True, timeout=140, check=True)
   packs = json.loads(cmd.stdout)
   filename = packs[0]["filename"]
   target = DIST / filename
   if not target.is_file():
    raise ValueError("npm pack returned missing file")
   n = target.stat().st_size
   if n < 100 or n > 45_000_000:
    raise ValueError(f"tarball size out of approved bounds: {n}")
   sha = hashlib.sha256(target.read_bytes()).hexdigest()
   result.update({"file": filename, "size": n, "sha256": sha,
                  "source": f"https://registry.npmjs.org/{name}/-/{filename}",
                  "npm_integrity": packs[0].get("integrity"),
                  "status": "DOWNLOADED_SHA256_VERIFIED"})
   with tarfile.open(target, "r:gz") as tf:
    members = tf.getmembers()
    # Some packages use LICENSE.md, LICENSE.txt, COPYING, etc.
    license_paths = [m.name for m in members if re.search(
      r"(^|/)(LICENSE|LICENCE|COPYING|NOTICE)(\.|$)", m.name, re.I) and m.isfile()]
    result["bundled_license_files"] = license_paths[:18]
    if not license_paths:
     result["license_text_status"] = "CHECK_PROVIDER_LICENSE"
    else:
     result["license_text_status"] = "BUNDLED_WITH_TARBALL"
   (META / (re.sub(r"[^A-Za-z0-9_.-]", "_", name)+"-"+version+".json")).write_text(
      json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
  except Exception as exc:
   result.update({"status": "HOLD_DOWNLOAD_FAILED", "error": str(exc)[:550]})
   errors.append(name)
  result["seconds"] = round(time.monotonic()-start,2)
  rows.append(result)
  print(f"{group} {name}: {result['status']} {result.get('version','')} {result.get('size',0)}",flush=True)

summary = {"date": "2026-11-10", "project": "NOX HELION",
  "scope": "extended cinematic and service dependency intake; NOT installed in active NOX",
  "packages_requested": len(rows),
  "packages_downloaded": sum(x["status"]=="DOWNLOADED_SHA256_VERIFIED" for x in rows),
  "packages_failed": len(errors),
  "failures": errors,
  "bytes": sum(x.get("size",0) for x in rows),
  "license_status": "Metadata and bundled texts only; provider usage terms require review",
  "user_facing_runtime": "NOT_TESTED", "gpu": "NOT_TESTED", "production": "UNMODIFIED",
  "files": rows,
}
(OUT/"NOX-EXTENDED-DEPENDENCIES-MANIFEST.json").write_text(
  json.dumps(summary, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
(OUT/"README-STATUS.txt").write_text(
  f"NOX HELION V19 expanded package download\n"
  f"Downloaded={summary['packages_downloaded']}/{len(rows)}; failed={len(errors)}\n"
  "These are candidate library source tarballs. Do not imply WebGL runtime integration.\n"
  "Some packages require paid API keys, license approval, backend, or user consent.\n"
  "Production remains unchanged.\n",encoding="utf-8")
print("NOX_EXTENDED_RESULT="+json.dumps({k:summary[k] for k in
   ["packages_requested","packages_downloaded","packages_failed","bytes","failures"]}), flush=True)
# Partial artifact still uploaded: real downloaded files and failed statuses remain auditable.
